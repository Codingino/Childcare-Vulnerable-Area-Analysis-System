"""이음: 초대형 육아 공동체 파일럿. Python 3.11+, SQLite, WSGI."""
import argparse, csv, hashlib, io, json, os, secrets, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('IEUM_DB', str(ROOT / 'data/ieum.sqlite3')))
MAX_MEMBERS = 50

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def init():
    with connect() as d:
        d.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY, token TEXT UNIQUE, cohort TEXT NOT NULL, consent INTEGER DEFAULT 0, consent_at REAL, created REAL);
        CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, member TEXT REFERENCES members(id) ON DELETE CASCADE, kind TEXT, title TEXT, body TEXT, status TEXT DEFAULT 'pending', created REAL);
        CREATE TABLE IF NOT EXISTS help(post INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE, helper TEXT REFERENCES members(id) ON DELETE SET NULL, offered REAL, completed REAL, research INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS replies(id INTEGER PRIMARY KEY, post INTEGER REFERENCES posts(id) ON DELETE CASCADE, member TEXT REFERENCES members(id) ON DELETE CASCADE, body TEXT, status TEXT DEFAULT 'pending', created REAL);
        CREATE TABLE IF NOT EXISTS reports(post INTEGER REFERENCES posts(id) ON DELETE CASCADE, member TEXT REFERENCES members(id) ON DELETE CASCADE, reason TEXT, PRIMARY KEY(post,member));
        CREATE TABLE IF NOT EXISTS surveys(member TEXT REFERENCES members(id) ON DELETE CASCADE, week TEXT, burden INTEGER, support INTEGER, search_minutes INTEGER, helped INTEGER, created REAL, PRIMARY KEY(member,week));
        CREATE TABLE IF NOT EXISTS actions(member TEXT REFERENCES members(id) ON DELETE CASCADE, day TEXT, kind TEXT, PRIMARY KEY(member,day,kind));
        ''')

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def invite(cohort):
    token = secrets.token_urlsafe(32)
    with connect() as d:
        if d.execute('SELECT COUNT(*) FROM members').fetchone()[0] >= MAX_MEMBERS:
            raise ValueError('파일럿 정원 50명에 도달했습니다.')
        d.execute('INSERT INTO members(id,token,cohort,created) VALUES(?,?,?,?)', (secrets.token_hex(12), digest(token), cohort, time.time()))
    return token

def clean(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'문자 입력은 1~{limit}자여야 합니다.')
    return value.strip()

def number(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('숫자 범위를 확인해 주세요.')
    return value

def response(start, status, data, content_type='application/json; charset=utf-8'):
    body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
    start(status, [('Content-Type', content_type), ('Content-Length', str(len(body))), ('Cache-Control','no-store'), ('X-Content-Type-Options','nosniff'), ('Referrer-Policy','no-referrer'), ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")])
    return [body]

def app(env, start):
    try:
        return route(env, start)
    except ValueError as e:
        return response(start, '400 Bad Request', {'error':str(e)})
    except Exception:
        # Never log submitted text, tokens or survey answers.
        return response(start, '500 Internal Server Error', {'error':'처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'})

def route(e, start):
    path, method = e.get('PATH_INFO','/'), e['REQUEST_METHOD']
    if path in ['/', '/app.js', '/style.css'] and method == 'GET':
        name = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
        mime = {'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[path]
        return response(start,'200 OK',(ROOT/'static'/name).read_bytes(),mime+'; charset=utf-8')
    if not path.startswith('/api/'):
        return response(start,'404 Not Found',{'error':'페이지가 없습니다.'})
    token = e.get('HTTP_AUTHORIZATION','').removeprefix('Bearer ')
    with connect() as d:
        m = d.execute('SELECT * FROM members WHERE token=?',(digest(token),)).fetchone()
        if not m:
            return response(start,'401 Unauthorized',{'error':'초대 코드를 확인해 주세요.'})
        mid = m['id']
        data = {}
        if method == 'POST':
            if e.get('CONTENT_TYPE','').split(';')[0] != 'application/json':
                raise ValueError('JSON 요청만 지원합니다.')
            size = int(e.get('CONTENT_LENGTH') or 0)
            if size < 1 or size > 10000: raise ValueError('요청 크기를 확인해 주세요.')
            try: data = json.loads(e['wsgi.input'].read(size))
            except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError('입력 형식을 확인해 주세요.')
            if not isinstance(data, dict): raise ValueError('입력 형식을 확인해 주세요.')
        if path == '/api/state' and method == 'GET':
            posts = [dict(r) for r in d.execute('''SELECT p.id,p.kind,p.title,p.body,p.created,p.status,p.member=? AS mine FROM posts p JOIN members u ON u.id=p.member WHERE u.cohort=? AND (p.status='approved' OR p.member=?) ORDER BY p.created DESC LIMIT 100''',(mid,m['cohort'],mid))]
            for p in posts:
                p['help'] = None
                h = d.execute('SELECT helper=? AS helping,helper IS NOT NULL AS matched,offered,completed FROM help WHERE post=?',(mid,p['id'])).fetchone()
                if h: p['help'] = dict(h)
                p['replies'] = [dict(r) for r in d.execute("SELECT id,body,status,member=? AS mine FROM replies WHERE post=? AND (status='approved' OR member=?) ORDER BY created LIMIT 100",(mid,p['id'],mid))]
            surveys = [dict(r) for r in d.execute('SELECT week,burden,support,search_minutes,helped FROM surveys WHERE member=? ORDER BY created',(mid,))]
            return response(start,'200 OK',{'cohort':m['cohort'],'consent':bool(m['consent']),'posts':posts,'surveys':surveys,'week':datetime.now(timezone.utc).strftime('%G-W%V')})
        if path == '/api/consent' and method == 'POST':
            if type(data.get('agree')) is not bool: raise ValueError('동의 여부를 선택해 주세요.')
            agree = data['agree']
            d.execute('UPDATE members SET consent=?,consent_at=? WHERE id=?',(int(agree),time.time() if agree else None,mid))
            if not agree:
                d.execute('DELETE FROM surveys WHERE member=?',(mid,))
                d.execute('DELETE FROM actions WHERE member=?',(mid,))
                d.execute('UPDATE help SET research=0 WHERE post IN (SELECT id FROM posts WHERE member=?)',(mid,))
        elif path == '/api/post' and method == 'POST':
            kind = data.get('kind')
            if kind not in ['질문','경험 나눔','함께하기','10분 도움']: raise ValueError('글 종류를 선택해 주세요.')
            if d.execute('SELECT COUNT(*) FROM posts WHERE member=? AND created>?',(mid,time.time()-86400)).fetchone()[0] >= 5: raise ValueError('하루에 글 5개까지 작성할 수 있습니다.')
            cur = d.execute('INSERT INTO posts(member,kind,title,body,created) VALUES(?,?,?,?,?)',(mid,kind,clean(data.get('title'),70),clean(data.get('body'),1200),time.time()))
            if kind == '10분 도움': d.execute('INSERT INTO help(post,research) VALUES(?,?)',(cur.lastrowid,int(m['consent'])))
        elif path in ['/api/offer','/api/release','/api/complete','/api/reply','/api/report','/api/delete-post'] and method == 'POST':
            pid = number(data.get('post'),1,2**53)
            p = d.execute('SELECT p.* FROM posts p JOIN members u ON u.id=p.member WHERE p.id=? AND u.cohort=? AND (p.status=\'approved\' OR p.member=?)',(pid,m['cohort'],mid)).fetchone()
            if not p: raise ValueError('게시물을 찾을 수 없습니다.')
            if path in ['/api/offer','/api/release','/api/complete']:
                h = d.execute('SELECT * FROM help WHERE post=?',(pid,)).fetchone()
                if not h or h['completed']: raise ValueError('이미 종료되었거나 도움 요청이 아닙니다.')
                if path == '/api/offer':
                    if p['member'] == mid or p['status'] != 'approved' or p['created'] < time.time()-7*86400: raise ValueError('지금 응답할 수 없는 요청입니다.')
                    changed = d.execute('UPDATE help SET helper=?,offered=? WHERE post=? AND helper IS NULL AND completed IS NULL',(mid,time.time(),pid)).rowcount
                    if not changed: raise ValueError('다른 분이 먼저 응답했습니다.')
                elif path == '/api/release':
                    if h['helper'] != mid: return response(start,'403 Forbidden',{'error':'응답한 분만 취소할 수 있습니다.'})
                    d.execute('UPDATE help SET helper=NULL,offered=NULL WHERE post=?',(pid,))
                else:
                    if p['member'] != mid or h['helper'] is None: return response(start,'403 Forbidden',{'error':'연결 후 요청자만 완료할 수 있습니다.'})
                    d.execute('UPDATE help SET completed=? WHERE post=?',(time.time(),pid))
            elif path == '/api/delete-post':
                if p['member'] != mid: return response(start,'403 Forbidden',{'error':'작성자만 삭제할 수 있습니다.'})
                d.execute('DELETE FROM posts WHERE id=?',(pid,))
            elif path == '/api/report':
                reason = data.get('reason')
                if reason not in ['개인정보','광고','부적절한 내용']: raise ValueError('신고 사유를 선택해 주세요.')
                d.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?)',(pid,mid,reason))
                d.execute("UPDATE posts SET status='pending' WHERE id=?",(pid,))
            else:
                if d.execute('SELECT COUNT(*) FROM replies WHERE member=? AND created>?',(mid,time.time()-86400)).fetchone()[0] >= 10: raise ValueError('하루에 답글 10개까지 작성할 수 있습니다.')
                d.execute('INSERT INTO replies(post,member,body,created) VALUES(?,?,?,?)',(pid,mid,clean(data.get('body'),600),time.time()))
        elif path == '/api/survey' and method == 'POST':
            if not m['consent']: return response(start,'403 Forbidden',{'error':'연구 참여에 동의한 경우에만 기록합니다.'})
            values = [number(data.get(k),a,b) for k,a,b in [('burden',1,5),('support',1,5),('search_minutes',0,600),('helped',0,50)]]
            week = datetime.now(timezone.utc).strftime('%G-W%V')
            d.execute('INSERT INTO surveys VALUES(?,?,?,?,?,?,?) ON CONFLICT(member,week) DO UPDATE SET burden=excluded.burden,support=excluded.support,search_minutes=excluded.search_minutes,helped=excluded.helped', (mid,week,*values,time.time()))
        elif path == '/api/action' and method == 'POST':
            if data.get('kind') not in ['childcare','benefits','family']: raise ValueError('알 수 없는 링크입니다.')
            if m['consent']:
                d.execute('INSERT OR IGNORE INTO actions VALUES(?,?,?)',(mid,datetime.now(timezone.utc).date().isoformat(),data['kind']))
        elif path == '/api/delete-account' and method == 'POST':
            d.execute('DELETE FROM members WHERE id=?',(mid,))
        else:
            return response(start,'404 Not Found',{'error':'지원하지 않는 요청입니다.'})
        return response(start,'200 OK',{'ok':True})

def export_csv():
    """Only consented paired-study data; no post text, tokens or invite mapping."""
    with connect() as d:
        rows = d.execute('SELECT s.member AS participant_id,m.cohort,s.week,s.burden,s.support,s.search_minutes,s.helped FROM surveys s JOIN members m ON m.id=s.member WHERE m.consent=1 ORDER BY s.member,s.created').fetchall()
        out = io.StringIO()
        w = csv.writer(out); w.writerow(['participant_id','cohort','week','burden','support','search_minutes','helped'])
        for r in rows: w.writerow([("'"+v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in r])
        return out.getvalue()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['serve','invite','review','approve','hide','export','export-help','purge'])
    parser.add_argument('--cohort',default='우리 동네 1기')
    parser.add_argument('--table',choices=['posts','replies'],default='posts')
    parser.add_argument('--id',type=int)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--output',default='data/research.csv')
    args = parser.parse_args(); init()
    if args.command == 'invite': print(invite(clean(args.cohort,40)))
    elif args.command == 'serve':
        print(f'이음: http://127.0.0.1:{args.port}')
        make_server('127.0.0.1',args.port,app).serve_forever()
    elif args.command == 'export-help':
        with connect() as d:
            rows=d.execute('SELECT p.id,p.member,m.cohort,p.created,h.offered,h.completed FROM help h JOIN posts p ON p.id=h.post JOIN members m ON m.id=p.member WHERE h.research=1 AND m.consent=1').fetchall()
            target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f); w.writerow(['request_id','participant_id','cohort','created','offered','completed'])
                for row in rows: w.writerow([("'"+v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row])
        print('도움 요청 연구 CSV 저장 완료. 외부 공개 금지.')
    elif args.command == 'export':
        target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(export_csv(),encoding='utf-8-sig'); print('연구 CSV 저장 완료. 외부 공개 금지.')
    elif args.command == 'purge':
        with connect() as d: d.execute('DELETE FROM members WHERE created<?',(time.time()-90*86400,))
        print('가입 90일이 지난 참여자와 연결 데이터 삭제 완료. 별도 백업도 삭제하세요.')
    else:
        with connect() as d:
            if args.command == 'review':
                for t in ['posts','replies','reports']:
                    print(t)
                    for row in d.execute('SELECT * FROM '+t): print(dict(row))
            else:
                if args.id is None: parser.error('--id가 필요합니다.')
                d.execute('UPDATE '+args.table+' SET status=? WHERE id=?',('approved' if args.command=='approve' else 'hidden',args.id))
