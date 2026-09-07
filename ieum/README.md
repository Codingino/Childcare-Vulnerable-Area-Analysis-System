# 이음 — 작은 도움으로 연결되는 부모 공동체

기존 어린이집 보육 취약 가능 지역 분석의 후속 탐구용 웹 앱입니다. 핵심은 **10분 도움 요청 → 이웃 응답 → 요청자의 실제 완료 확인**입니다. 포인트·보답 의무 없이 도움을 받을 수 있습니다.

**현재 상태:** 로컬 실행 가능한 서버·모바일 대응 웹 UI·연구 CSV·분석 도구를 구현했습니다. GitHub 소스 전달용 버전이며 실제 공개 서버 배포, 참여자 모집, 효과 검증은 아직 하지 않았습니다. 실제 데이터와 가짜 시드 데이터 모두 포함하지 않습니다.

## 포함 기능

- 개인 초대 코드와 모임별 접근 분리, 최대 50명
- 작은 도움 요청, 중복 응답 방지, 응답 취소, 요청자 완료 확인, 7일 응답 기한
- 질문·경험 공유·함께하기, 검토형 답글, 신고와 작성자 삭제
- 복지로·아이사랑·가족센터 공식 안내 연결
- 연구 참여 선택·철회, 주간 설문, 내 기록, 계정 삭제
- CLI 운영자 검토·승인·숨김·보관기간 삭제
- 동의자 연구 CSV, 짝지어진 사전·사후 기술통계, 7일 도움 연결 통계
- 생활권 공급지표와 자체 가중치 민감도 분석 도구

## 빠른 실행

Python 3.11 이상. 로컬 시연은 외부 패키지 없이 실행됩니다.

```bash
cd ieum
python server.py invite --cohort '우리 동네 1기'
python server.py serve
```

첫 명령의 개인 코드를 보관하고 `http://127.0.0.1:8000`에서 입력하세요. 다른 참여자는 `invite`를 다시 실행해 다른 코드를 발급합니다. 운영자가 확인한 성인 보호자에게만 전달하세요. 코드는 저장소에 커밋하지 마세요. 서버를 끄려면 Ctrl+C.

별도 터미널에서 검토합니다.

```bash
python server.py review
python server.py approve --table posts --id 1
python server.py approve --table replies --id 1
python server.py hide --table posts --id 1
```

숫자는 실제 검토 결과의 ID로 바꾸세요. 공개 후 이용자가 새로고침하면 반영됩니다. 신고된 글은 자동으로 재검토 대기가 됩니다. 답글을 숨길 때는 `--table replies`를 지정합니다.

## 연구 데이터 추출

```bash
python server.py export --output data/research.csv
python server.py export-help --output data/help.csv
python analyze.py data/research.csv --help-csv data/help.csv
python server.py purge
```

`data/`는 Git에서 제외합니다. CSV는 개인 연결이 가능한 연구 원본이므로 공개하지 마세요. 분석은 동의자만 대상으로 하며 응답 수·탈락·자기선택 편향을 함께 보고해야 합니다. 5명 미만 짝 자료에서는 공개용 변화값을 표시하지 않습니다. 도움 통계는 최소 7일 관찰한 요청이 있어야 계산합니다.

생활권 공공데이터 분석은 `docs/context-template.csv`의 헤더에 실제 기준일과 집계 수치를 넣은 별도 파일을 만든 뒤 실행합니다. 실제 부모 주소는 필요하지 않습니다.

```bash
python context.py data/context.csv
```

## 인터넷 운영

실제 휴대폰 공동 사용에는 별도 HTTPS 서버·영속 디스크가 필요합니다. GitHub Pages는 이 서버를 실행하지 않습니다. `server.py serve`는 로컬 개발용입니다. 운영자는 HTTPS 프록시 뒤에서 다음처럼 WSGI 서버를 실행할 수 있습니다.

```bash
python -m pip install -r requirements.txt
python -m gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 30 wsgi:app
```

`IEUM_DB` 환경변수로 영속 저장소의 DB 경로를 지정할 수 있습니다. 지정하지 않으면 `data/ieum.sqlite3`입니다. 운영 전 [운영 안내](docs/OPERATIONS.md)의 HTTPS·서버 한도·검토·백업 삭제 절차를 구성하세요. 공급자 배포 자동화나 계정 생성은 포함하지 않습니다.

## 검증

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

서버 테스트: 인증, 모임 격리, 작성자 권한, 검토·신고, 도움 상태 전이, 중복 응답, 연구 동의·철회, 계정 삭제, 입력 한도, 소표본 억제. 실제 브라우저 시각 검증·운영 부하 테스트는 수행하지 않았습니다.

## 탐구 자료

- [시장 비교와 연구 설계](docs/RESEARCH.md)
- [운영 비용·수익 가설·개인정보·운영일지](docs/OPERATIONS.md)

최초성이나 우울증 치료 효과를 주장하지 않습니다. 기존 보고서에서 제시한 공급 접근성과 부모의 경험을 연결하는 **탐색적 운영 실험**입니다.
