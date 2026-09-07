import io,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from analyze import summarize

class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test.db';server.init()
        self.a=server.invite('A');self.b=server.invite('A');self.c=server.invite('B')
    def tearDown(self): self.tmp.cleanup()
    def request(self,path,token=None,data=None):
        body=json.dumps(data).encode();out=[]
        env={'PATH_INFO':'/api/'+path,'REQUEST_METHOD':'GET' if data is None else 'POST','HTTP_AUTHORIZATION':'Bearer '+(token or ''),'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)}
        result=b''.join(server.app(env,lambda s,h:out.append(s)))
        return int(out[0].split()[0]),json.loads(result)
    def post(self):
        self.assertEqual(self.request('post',self.a,{'kind':'10분 도움','title':'지원정보 같이 찾기','body':'공식 링크가 궁금해요.'})[0],200)
        with server.connect() as d:d.execute("UPDATE posts SET status='approved'")
    def test_auth_and_group_isolation(self):
        self.assertEqual(self.request('state')[0],401);self.post()
        self.assertEqual(len(self.request('state',self.c)[1]['posts']),0)
        self.assertEqual(self.request('offer',self.c,{'post':1})[0],400)
    def test_moderation_and_owner(self):
        self.request('post',self.a,{'kind':'질문','title':'안녕','body':'반가워요'})
        self.assertEqual(self.request('state',self.b)[1]['posts'],[])
        with server.connect() as d:d.execute("UPDATE posts SET status='approved'")
        self.assertEqual(self.request('delete-post',self.b,{'post':1})[0],403)
        self.assertEqual(self.request('report',self.b,{'post':1,'reason':'개인정보'})[0],200)
        self.assertEqual(self.request('state',self.b)[1]['posts'],[])
    def test_help_lifecycle_and_double_offer(self):
        self.post();self.assertEqual(self.request('offer',self.a,{'post':1})[0],400)
        self.assertEqual(self.request('offer',self.b,{'post':1})[0],200)
        self.assertEqual(self.request('offer',self.b,{'post':1})[0],400)
        self.assertEqual(self.request('complete',self.b,{'post':1})[0],403)
        self.assertEqual(self.request('complete',self.a,{'post':1})[0],200)
        self.assertEqual(self.request('release',self.b,{'post':1})[0],400)
    def test_consent_withdrawal_and_delete(self):
        survey={'burden':3,'support':2,'search_minutes':40,'helped':0}
        self.assertEqual(self.request('survey',self.a,survey)[0],403)
        self.request('consent',self.a,{'agree':True});self.post()
        self.assertEqual(self.request('survey',self.a,survey)[0],200)
        self.request('survey',self.a,survey)
        self.assertEqual(len(self.request('state',self.a)[1]['surveys']),1)
        self.request('consent',self.a,{'agree':False})
        self.assertEqual(len(server.export_csv().splitlines()),1)
        with server.connect() as d:self.assertEqual(d.execute('SELECT research FROM help').fetchone()[0],0)
        self.request('delete-account',self.a,{})
        self.assertEqual(self.request('state',self.a)[0],401)
        with server.connect() as d:self.assertEqual(d.execute('SELECT COUNT(*) FROM posts').fetchone()[0],0)
    def test_validation_and_cap(self):
        self.request('consent',self.a,{'agree':True})
        self.assertEqual(self.request('survey',self.a,{'burden':99,'support':3,'search_minutes':1,'helped':0})[0],400)
        for i in range(5):self.assertEqual(self.request('post',self.a,{'kind':'질문','title':'글','body':'본문'})[0],200)
        self.assertEqual(self.request('post',self.a,{'kind':'질문','title':'글','body':'본문'})[0],400)
    def test_small_sample_suppression(self):
        self.assertIn('5명 미만',summarize([])['paired_change'])

if __name__=='__main__':unittest.main()
