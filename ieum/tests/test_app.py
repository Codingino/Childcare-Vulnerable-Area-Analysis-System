import io,json,sys,tempfile,time,unittest,sqlite3,struct
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,auth
from analyze import summarize

class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test.db';server.init()
        self.a=self.register('parent_a','10.0.0.1');self.b=self.register('parent_b','10.0.0.2');self.c=self.register('parent_c','10.0.0.3')
        with server.connect() as d:d.execute("UPDATE members SET cohort='closed legacy' WHERE username='parent_c'")
    def tearDown(self):self.tmp.cleanup()
    def request(self,path,cookie='',data=None,ip='10.0.1.1',header=True):
        body=json.dumps(data).encode();out=[]
        env={'PATH_INFO':'/api/'+path,'REQUEST_METHOD':'GET' if data is None else 'POST','HTTP_COOKIE':cookie,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'REMOTE_ADDR':ip}
        if header:env['HTTP_X_IEUM_REQUEST']='1'
        result=b''.join(server.app(env,lambda s,h:out.append((s,dict(h)))))
        self.headers=out[0][1]
        return int(out[0][0].split()[0]),json.loads(result)
    def register(self,name,ip):
        code,data=self.request('auth/register',data={'username':name,'password':'long-password-123','adult':True,'terms':True},ip=ip)
        self.assertEqual(code,200,data)
        return self.headers['Set-Cookie'].split(';')[0]
    def post(self,consent=False):
        if consent:self.request('consent',self.a,{'agree':True})
        code,data=self.request('post',self.a,{'kind':'10분 도움','title':'정리 부탁','body':'공식 링크 두 개만 알려주세요.','mode':'listen','minutes':5})
        self.assertEqual(code,200,data)
        with server.connect() as d:d.execute("UPDATE posts SET status='approved'")
    def test_password_and_cookie_auth(self):
        self.assertEqual(self.request('state')[0],401)
        self.assertEqual(self.request('state',self.a)[0],200)
        self.assertEqual(self.request('auth/login',data={'username':'parent_a','password':'wrong'})[0],401)
        with patch.dict('os.environ',{'IEUM_HTTPS':'1'}):
            self.assertEqual(self.request('auth/login',data={'username':'parent_a','password':'long-password-123'})[0],200)
            self.assertIn('HttpOnly',self.headers['Set-Cookie']);self.assertIn('Secure',self.headers['Set-Cookie'])
        with server.connect() as d:
            self.assertNotIn('long-password',d.execute("SELECT password FROM members WHERE username='parent_a'").fetchone()[0])
    def test_logout_expiry_csrf(self):
        self.assertEqual(self.request('consent',self.a,{'agree':True},header=False)[0],403)
        self.request('auth/logout',self.a,{})
        self.assertEqual(self.request('state',self.a)[0],401)
        with server.connect() as d:d.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.request('state',self.b)[0],401)
    def test_registration_validation_limit(self):
        self.assertEqual(self.request('auth/register',data={'username':'new','password':'long-password-123','adult':False,'terms':True})[0],400)
        self.assertEqual(self.request('auth/register',data={'username':'parent_a','password':'long-password-123','adult':True,'terms':True})[0],400)
        for i in range(16):code,_=self.request('auth/login',data={'username':'absent','password':'wrong'},ip='limit-test')
        self.assertEqual(code,429)
        with patch.object(server,'MAX_MEMBERS',3):
            self.assertEqual(self.request('auth/register',data={'username':'full','password':'long-password-123','adult':True,'terms':True},ip='full')[0],409)
    def test_isolation_moderation_owner(self):
        self.post()
        self.assertEqual(self.request('state',self.c)[1]['posts'],[])
        self.assertEqual(self.request('offer',self.c,{'post':1})[0],400)
        self.assertEqual(self.request('delete-post',self.b,{'post':1})[0],403)
        self.request('report',self.b,{'post':1,'reason':'個人情報'})
        self.assertEqual(self.request('report',self.b,{'post':1,'reason':'개인정보'})[0],200)
        self.assertEqual(self.request('state',self.b)[1]['posts'],[])
    def test_help_completion_feedback_private(self):
        self.post(consent=True)
        self.assertEqual(self.request('offer',self.a,{'post':1})[0],400)
        self.assertEqual(self.request('offer',self.b,{'post':1})[0],200)
        self.assertEqual(self.request('offer',self.b,{'post':1})[0],400)
        self.assertEqual(self.request('complete',self.b,{'post':1})[0],403)
        self.assertEqual(self.request('complete',self.a,{'post':1,'relief':4,'followup':0})[0],200)
        with server.connect() as d:self.assertEqual(d.execute('SELECT relief,followup FROM help').fetchone()[:],(4,0))
        other=self.request('state',self.b)[1]['posts'][0]['help']
        self.assertNotIn('relief',other);self.assertFalse(other['research'])
        self.request('consent',self.a,{'agree':False})
        with server.connect() as d:self.assertEqual(d.execute('SELECT research,relief,followup FROM help').fetchone()[:],(0,None,None))
    def test_no_retrospective_consent_and_delete(self):
        self.post();self.request('consent',self.a,{'agree':True});self.request('offer',self.b,{'post':1})
        self.request('complete',self.a,{'post':1,'relief':5,'followup':0})
        with server.connect() as d:self.assertIsNone(d.execute('SELECT relief FROM help').fetchone()[0])
        survey={'burden':3,'support':2,'search_minutes':40,'helped':0}
        self.request('survey',self.a,survey);self.request('survey',self.a,survey)
        self.assertEqual(len(self.request('state',self.a)[1]['surveys']),1)
        self.request('consent',self.a,{'agree':False});self.assertEqual(len(server.export_csv().splitlines()),1)
        self.request('delete-account',self.a,{})
        self.assertEqual(self.request('state',self.a)[0],401)
        with server.connect() as d:self.assertEqual(d.execute('SELECT COUNT(*) FROM posts').fetchone()[0],0)
    def test_expired_request_and_invalid_mode_rollback(self):
        self.assertEqual(self.request('post',self.a,{'kind':'10분 도움','title':'a','body':'b','mode':'invalid'})[0],400)
        with server.connect() as d:self.assertEqual(d.execute('SELECT COUNT(*) FROM posts').fetchone()[0],0)
        self.post()
        with server.connect() as d:d.execute('UPDATE posts SET created=?',(time.time()-8*86400,))
        self.assertEqual(self.request('offer',self.b,{'post':1})[0],400)
    def test_pwa_assets_without_login(self):
        for path,mime in [('/','text/html'),('/manifest.webmanifest','application/manifest+json'),('/sw.js','text/javascript'),('/icon-192.png','image/png'),('/icon-512.png','image/png')]:
            out=[];body=b''.join(server.app({'PATH_INFO':path,'REQUEST_METHOD':'GET'},lambda s,h:out.append((s,dict(h)))))
            self.assertEqual(out[0][0],'200 OK');self.assertEqual(out[0][1]['Content-Type'],mime)
            if path.endswith('.png'):self.assertEqual(struct.unpack('>II',body[16:24]),(int(path.split('-')[1].split('.')[0]),)*2)
        manifest=json.loads((server.ROOT/'static/manifest.webmanifest').read_text());self.assertEqual(manifest['display'],'standalone')
    def test_v1_schema_migration(self):
        old=Path(self.tmp.name)/'old.db';server.DB=old
        with sqlite3.connect(old) as d:
            d.execute('CREATE TABLE members(id TEXT PRIMARY KEY,token TEXT UNIQUE,cohort TEXT NOT NULL,consent INTEGER DEFAULT 0,consent_at REAL,created REAL)')
            d.execute("INSERT INTO members VALUES('legacy','oldhash','private',0,NULL,1)")
        server.init();server.init()
        with server.connect() as d:
            self.assertEqual(d.execute("SELECT cohort FROM members WHERE id='legacy'").fetchone()[0],'private')
            self.assertIsNone(d.execute("SELECT username FROM members WHERE id='legacy'").fetchone()[0])
        self.assertEqual(self.request('state',cookie='ieum_session=oldhash')[0],401)
    def test_analysis_denominator_and_suppression(self):
        self.assertIn('5명 미만',summarize([])['paired_change'])
        now=time.time();rows=[{'participant_id':str(i),'created':str(now-8*86400),'offered':str(now-7.9*86400) if i<2 else '', 'completed':str(now-7*86400) if i==0 else ''} for i in range(5)]
        metrics=summarize([],rows)['help_metrics'];self.assertEqual(metrics['connection_rate_7d'],.4);self.assertEqual(metrics['completion_rate_7d'],.2);self.assertEqual(metrics['unmatched_7d'],3)

if __name__=='__main__':unittest.main()
