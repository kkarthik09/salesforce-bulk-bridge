import tempfile
import unittest
from pathlib import Path
from bridge import Bridge,DemoTransport,RecoveryRequired,SalesforceHTTP,validate_csv
CSV='External_Id__c,Name\nx1,One\nx2,Two\n'
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'checkpoint.json';self.fake=DemoTransport();self.b=Bridge(self.fake,self.path,sleep=lambda _:None)
    def test_lifecycle_and_replay(self):
        self.assertEqual('JobComplete',self.b.run(CSV,'Account','External_Id__c')['outcome']);self.b.run(CSV,'Account','External_Id__c')
        self.assertEqual(['POST','PUT','GET','PATCH','GET'],[m for m,_ in self.fake.calls])
    def test_changed_input(self):
        self.b.run(CSV,'Account','External_Id__c')
        with self.assertRaises(ValueError):self.b.run(CSV.replace('x1','x3'),'Account','External_Id__c')
    def test_destination_binding(self):
        self.b.run(CSV,'Account','External_Id__c');self.fake.base='different-destination'
        with self.assertRaises(ValueError):self.b.run(CSV,'Account','External_Id__c')
    def test_ambiguous_creation_not_retried(self):
        class Lost(DemoTransport):
            def request(self,*a,**k):raise TimeoutError('lost')
        with self.assertRaises(TimeoutError):Bridge(Lost(),self.path).run(CSV,'Account','External_Id__c')
        with self.assertRaises(RecoveryRequired):self.b.run(CSV,'Account','External_Id__c')
        self.assertEqual([],self.fake.calls)
    def test_poll_resume(self):
        class Slow(DemoTransport):
            def request(self,method,suffix='',body=None,content_type='application/json'):
                result=super().request(method,suffix,body,content_type)
                if method=='PATCH':self.state='InProgress'
                return result
        slow=Slow();b=Bridge(slow,self.path,sleep=lambda _:None)
        with self.assertRaises(TimeoutError):b.run(CSV,'Account','External_Id__c',max_polls=1)
        slow.state='JobComplete';self.assertEqual('JobComplete',b.run(CSV,'Account','External_Id__c')['outcome']);self.assertEqual(1,sum(m=='PUT' for m,_ in slow.calls))
    def test_bad_csv(self):
        for text in ('','Name\nx\n','External_Id__c,Name\nx,a\nx,b\n','External_Id__c,Name\nx\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):validate_csv(text,'External_Id__c')
    def test_origins(self):
        for url in ('http://demo.my.salesforce.com','https://evil.example','https://demo.my.salesforce.com/path','https://demo.my.salesforce.com.evil.example'):
            with self.subTest(url=url),self.assertRaises(ValueError):SalesforceHTTP(url,'fake','v66.0')
if __name__=='__main__':unittest.main()
