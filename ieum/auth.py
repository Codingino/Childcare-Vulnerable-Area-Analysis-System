"""Password accounts and revocable HttpOnly sessions; no invitation codes."""
import hashlib, hmac, json, os, re, secrets, sqlite3, time
from http.cookies import SimpleCookie, CookieError

ITERATIONS = 600_000
TTL = 14 * 86400
RATE_SECRET = secrets.token_bytes(32)

def migrate(d):
    columns={r['name'] for r in d.execute('PRAGMA table_info(members)')}
    for name,definition in [('username','TEXT'),('password','TEXT')]:
        if name not in columns: d.execute(f'ALTER TABLE members ADD COLUMN {name} {definition}')
    d.executescript('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_members_username ON members(username);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, member TEXT REFERENCES members(id) ON DELETE CASCADE, expires REAL);
    CREATE INDEX IF NOT EXISTS idx_sessions_member ON sessions(member);
    CREATE TABLE IF NOT EXISTS auth_limits(key TEXT PRIMARY KEY, count INTEGER, expires REAL);
    ''')

def password_hash(password):
    if not isinstance(password,str) or not 10<=len(password)<=128:
        raise ValueError('비밀번호는 10~128자로 입력해 주세요.')
    salt=secrets.token_hex(16)
    value=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return f'{salt}:{value}'

def password_matches(password,stored):
    if not isinstance(password,str) or len(password)>128:return False
    salt,expected=(stored or ('00'*16+':'+ '00'*32)).split(':')
    actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return hmac.compare_digest(actual,expected)

def username(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_]{3,24}',value):
        raise ValueError('아이디는 영문·숫자·밑줄 3~24자로 입력해 주세요.')
    return value.lower()

def session_key(e):
    try:
        c=SimpleCookie();c.load(e.get('HTTP_COOKIE',''))
        token=c['ieum_session'].value if 'ieum_session' in c else ''
    except CookieError:token=''
    return hashlib.sha256(token.encode()).hexdigest()

def current(d,e):
    return d.execute('SELECT m.* FROM members m JOIN sessions s ON s.member=m.id WHERE s.token=? AND s.expires>?',(session_key(e),time.time())).fetchone()

def read_json(e):
    if e.get('CONTENT_TYPE','').split(';')[0]!='application/json':raise ValueError('JSON 요청이 필요합니다.')
    size=int(e.get('CONTENT_LENGTH') or 0)
    if not 1<=size<=10000:raise ValueError('요청 크기를 확인해 주세요.')
    try:data=json.loads(e['wsgi.input'].read(size))
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('입력 형식을 확인해 주세요.')
    if not isinstance(data,dict):raise ValueError('입력 형식을 확인해 주세요.')
    return data

def cookie(token,clear=False):
    secure='; Secure' if os.environ.get('IEUM_HTTPS')=='1' else ''
    return f'ieum_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={0 if clear else TTL}{secure}'

def process(e,start,connect,response,max_members):
    path=e['PATH_INFO']
    if e['REQUEST_METHOD']!='POST':return response(start,'405 Method Not Allowed',{'error':'POST 요청이 필요합니다.'})
    data=read_json(e)
    if path not in ['/api/auth/register','/api/auth/login','/api/auth/logout']:
        return response(start,'404 Not Found',{'error':'지원하지 않는 요청입니다.'})
    with connect() as d:
        if path.endswith('/logout'):
            d.execute('DELETE FROM sessions WHERE token=?',(session_key(e),))
            return response(start,'200 OK',{'ok':True},extra=[('Set-Cookie',cookie('',True))])
    # Separate committed transaction: invalid attempts must still count.
    key=hmac.new(RATE_SECRET,(e.get('REMOTE_ADDR','local')+path).encode(),hashlib.sha256).hexdigest()
    now=time.time();limit=5 if path.endswith('/register') else 15
    with connect() as d:
        d.execute('DELETE FROM auth_limits WHERE expires<?',(now,))
        d.execute('INSERT INTO auth_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now+900))
        hits=d.execute('SELECT count FROM auth_limits WHERE key=?',(key,)).fetchone()[0]
    if hits>limit:return response(start,'429 Too Many Requests',{'error':'시도가 많습니다. 15분 후 다시 시도해 주세요.'})
    name=username(data.get('username'));password=data.get('password')
    with connect() as d:
        if path.endswith('/register'):
            if data.get('adult') is not True or data.get('terms') is not True:
                raise ValueError('성인 보호자 여부와 이용 안내를 확인해 주세요.')
            encoded=password_hash(password)
            d.execute('BEGIN IMMEDIATE')
            if d.execute('SELECT COUNT(*) FROM members').fetchone()[0]>=max_members:
                return response(start,'409 Conflict',{'error':'시범 운영 정원에 도달했습니다. 새 가입을 잠시 쉬고 있어요.'})
            mid=secrets.token_hex(12)
            try:
                d.execute('INSERT INTO members(id,token,cohort,created,username,password) VALUES(?,?,?,?,?,?)',(mid,None,'열린 이웃',now,name,encoded))
            except sqlite3.IntegrityError:raise ValueError('이미 사용 중인 아이디입니다.')
        else:
            m=d.execute('SELECT * FROM members WHERE username=?',(name,)).fetchone()
            if not password_matches(password,m['password'] if m else None):
                return response(start,'401 Unauthorized',{'error':'아이디 또는 비밀번호가 맞지 않습니다.'})
            mid=m['id']
        token=secrets.token_urlsafe(32)
        d.execute('DELETE FROM sessions WHERE expires<?',(now,))
        d.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),mid,now+TTL))
        return response(start,'200 OK',{'ok':True},extra=[('Set-Cookie',cookie(token))])
