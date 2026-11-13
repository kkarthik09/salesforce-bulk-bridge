"""Checkpointed Salesforce Bulk API 2.0 upsert; local fake transport by default."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

class RecoveryRequired(RuntimeError):pass

def validate_csv(text,external_id):
    reader=csv.DictReader(io.StringIO(text));headers=reader.fieldnames
    if not headers or external_id not in headers:raise ValueError('external ID column required')
    if len(set(headers))!=len(headers):raise ValueError('duplicate headers')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',h) for h in headers):raise ValueError('simple field API names required')
    seen=set();rows=0
    for row in reader:
        if None in row or any(v is None for v in row.values()):raise ValueError('ragged CSV row')
        key=row[external_id].strip()
        if not key or key in seen:raise ValueError('external IDs must be nonempty and unique')
        seen.add(key);rows+=1
    if not rows:raise ValueError('data rows required')
    return rows

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.checkpoint-')
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

class SalesforceHTTP:
    def __init__(self,instance,token,api_version,sleep=time.sleep):
        u=urllib.parse.urlsplit(instance);host=u.hostname or ''
        if u.scheme!='https' or not host.endswith('.my.salesforce.com') or u.username or u.password or u.port or u.query or u.fragment or u.path not in ('','/'):
            raise ValueError('HTTPS My Domain *.my.salesforce.com origin required')
        if not re.fullmatch(r'v\d+\.0',api_version):raise ValueError('invalid API version')
        if not token:raise ValueError('token required')
        self.base=instance.rstrip('/')+'/services/data/'+api_version+'/jobs/ingest'
        self.token,self.sleep=token,sleep;self.opener=urllib.request.build_opener(NoRedirect())
    def request(self,method,suffix='',body=None,content_type='application/json'):
        data=body.encode() if isinstance(body,str) else json.dumps(body).encode() if body is not None else None
        headers={'Authorization':'Bearer '+self.token,'Content-Type':content_type,'Accept':'application/json'}
        attempts=3 if method=='GET' else 1
        for attempt in range(attempts):
            try:
                req=urllib.request.Request(self.base+suffix,data=data,headers=headers,method=method)
                with self.opener.open(req,timeout=30) as res:
                    raw=res.read().decode();return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if method!='GET' or e.code not in (429,500,502,503,504) or attempt==attempts-1:
                    raise RuntimeError('Salesforce HTTP status '+str(e.code)) from None
                delay=e.headers.get('Retry-After','')
                self.sleep(min(float(delay),60) if delay.isdigit() else 2**attempt)

class Bridge:
    def __init__(self,transport,checkpoint,sleep=time.sleep):
        self.transport,self.path,self.sleep=transport,Path(checkpoint),sleep
    def run(self,text,object_name,external_id,max_polls=20,poll_seconds=2):
        if not all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',s) for s in (object_name,external_id)):raise ValueError('invalid API name')
        if max_polls<1 or poll_seconds<0:raise ValueError('invalid poll settings')
        rows=validate_csv(text,external_id)
        destination=getattr(self.transport,'base','local-demo')
        identity=hashlib.sha256(('\0'.join([destination,object_name,external_id,text])).encode()).hexdigest()
        state=json.loads(self.path.read_text()) if self.path.exists() else dict(fingerprint=identity,rows=rows,phase='new')
        if state['fingerprint']!=identity:raise ValueError('checkpoint belongs to different data, destination or configuration')
        def checkpoint(phase,**updates):state.update(phase=phase,**updates);save(self.path,state)
        if state['phase'] in ('creating','uploading'):
            raise RecoveryRequired('Previous mutation outcome is ambiguous. Inspect the remote job before restarting. Do not blindly remove the checkpoint.')
        if state['phase']=='new':
            checkpoint('creating')
            result=self.transport.request('POST',body=dict(object=object_name,operation='upsert',externalIdFieldName=external_id,contentType='CSV',lineEnding='LF'))
            job_id=result['id']
            if not re.fullmatch(r'[A-Za-z0-9]{15,18}',job_id):raise ValueError('invalid remote job ID')
            checkpoint('created',job_id=job_id)
        if not re.fullmatch(r'[A-Za-z0-9]{15,18}',state['job_id']):raise ValueError('invalid checkpoint job ID')
        job='/'+state['job_id']
        if state['phase']=='created':
            checkpoint('uploading');self.transport.request('PUT',job+'/batches',text,'text/csv');checkpoint('uploaded')
        if state['phase'] in ('uploaded','closing'):
            info=self.transport.request('GET',job)
            if info['state']=='Open':
                checkpoint('closing');self.transport.request('PATCH',job,{'state':'UploadComplete'})
            elif info['state'] in ('Failed','Aborted'):
                checkpoint('terminal',outcome=info['state']);return state
            checkpoint('polling')
        if state['phase']=='terminal':return state
        for _ in range(max_polls):
            info=self.transport.request('GET',job)
            if info['state'] in ('JobComplete','Failed','Aborted'):
                checkpoint('terminal',outcome=info['state'],processed=info.get('numberRecordsProcessed',0),failed=info.get('numberRecordsFailed',0));return state
            if info['state'] not in ('UploadComplete','InProgress'):raise RecoveryRequired('Unexpected state: '+info['state'])
            self.sleep(poll_seconds)
        raise TimeoutError('Poll budget exhausted; re-run with same checkpoint to resume')

class DemoTransport:
    def __init__(self):self.state='Open';self.calls=[]
    def request(self,method,suffix='',body=None,content_type='application/json'):
        self.calls.append((method,suffix))
        if method=='POST':return {'id':'750000000000001AAA'}
        if method=='PATCH':self.state='JobComplete'
        if method=='GET':return dict(state=self.state,numberRecordsProcessed=2,numberRecordsFailed=0)
        return {}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',default='sample.csv');p.add_argument('--checkpoint',default='checkpoint.json');p.add_argument('--object',default='Account');p.add_argument('--external-id',default='External_Id__c');p.add_argument('--api-version',default='v66.0');p.add_argument('--live',action='store_true');a=p.parse_args()
    transport=SalesforceHTTP(os.environ['SF_INSTANCE_URL'],os.environ['SF_ACCESS_TOKEN'],a.api_version) if a.live else DemoTransport()
    print(json.dumps(Bridge(transport,a.checkpoint).run(Path(a.csv).read_text(),a.object,a.external_id),indent=2))
