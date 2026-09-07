"""Local launcher: python start.py. Opens the app; creates no account automatically."""
import argparse, threading, webbrowser
from wsgiref.simple_server import make_server
import server

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);args=p.parse_args()
    server.init()
    with make_server('127.0.0.1',args.port,server.app) as httpd:
        url=f'http://127.0.0.1:{args.port}'
        print(f'이음: {url}\n종료하려면 이 창에서 Ctrl+C를 누르세요.')
        timer=threading.Timer(.5,lambda:webbrowser.open(url));timer.daemon=True;timer.start()
        try:httpd.serve_forever()
        except KeyboardInterrupt:pass
