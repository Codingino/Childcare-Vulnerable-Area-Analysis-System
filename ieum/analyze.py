"""CSV export analysis. python analyze.py data/research.csv --help-csv data/help.csv"""
import argparse, csv, json, statistics, time

def summarize(rows, help_rows=None):
    grouped={}
    for row in rows: grouped.setdefault(row['participant_id'],[]).append(row)
    paired=[]
    for values in grouped.values():
        ordered=sorted(values,key=lambda r:r['week'])
        if len(ordered)>=2: paired.append((ordered[0],ordered[-1]))
    result={'participants':len(grouped),'paired_participants':len(paired),'single_response_participants':len(grouped)-len(paired),'interpretation':'자발적 참여자 내 기술통계. 인과효과·우울증 개선·지역 전체의 효과를 의미하지 않음.'}
    if len(paired)<5:
        result['paired_change']='5명 미만: 공개용 변화값을 표시하지 않음'
    else:
        result['mean_last_minus_first']={k:round(statistics.mean(int(b[k])-int(a[k]) for a,b in paired),2) for k in ['burden','support','search_minutes','helped']}
        result['paired_week_intervals']=[len(set(r['week'] for r in grouped[a['participant_id']])) for a,b in paired]
    if help_rows is not None:
        # Use a full 7-day observation window, including unresolved requests.
        mature=[r for r in help_rows if float(r['created'])<=time.time()-7*86400]
        result['help_eligible_requests']=len(mature)
        if len({r['participant_id'] for r in mature})<5:
            result['help_metrics']='요청자 5명 미만: 공개용 연결 통계 비표시'
        else:
            matched=[r for r in mature if r['offered'] and float(r['offered'])-float(r['created'])<=7*86400]
            done=[r for r in mature if r['completed'] and float(r['completed'])-float(r['created'])<=7*86400]
            result['help_metrics']={'connection_rate_7d':len(matched)/len(mature),'completion_rate_7d':len(done)/len(mature),'unmatched_7d':len(mature)-len(matched),'median_response_hours_among_matched':statistics.median((float(r['offered'])-float(r['created']))/3600 for r in matched) if matched else None}
        feedback=[r for r in help_rows if r.get('completed') and r.get('relief') not in [None,'']]
        followup=[r for r in help_rows if r.get('completed') and r.get('followup') not in [None,'']]
        fit=[r for r in help_rows if r.get('completed') and r.get('fit') not in [None,'']]
        result['completion_feedback']={
            'response_fit_rate':statistics.mean(int(r['fit']) for r in fit) if len({r['participant_id'] for r in fit})>=5 else '응답자 5명 미만: 비표시',
            'mean_reported_relief':round(statistics.mean(int(r['relief']) for r in feedback),2) if len({r['participant_id'] for r in feedback})>=5 else '응답자 5명 미만: 비표시',
            'followup_required_rate':statistics.mean(int(r['followup']) for r in followup) if len({r['participant_id'] for r in followup})>=5 else '응답자 5명 미만: 비표시',
            'note':'선택 응답. 자기보고 및 요청 건수 가중 집계이며 개인별 효과가 아님.'}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('csv');p.add_argument('--help-csv');a=p.parse_args()
    with open(a.csv,encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    helps=None
    if a.help_csv:
        with open(a.help_csv,encoding='utf-8-sig') as f: helps=list(csv.DictReader(f))
    print(json.dumps(summarize(rows,helps),ensure_ascii=False,indent=2))

