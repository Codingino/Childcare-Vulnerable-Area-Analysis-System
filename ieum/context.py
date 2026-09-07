"""지역 집계 CSV만 사용. 실제 주소·개인정보 불필요. 표준입력 아닌 명시적 파일 경로."""
import csv,json,math,sys

def compute(r):
    count,capacity,enrolled,public,pop,radius=[float(r[k]) for k in ['facilities','capacity','enrolled','public_capacity','children','radius_km']]
    if not all(math.isfinite(x) for x in [count,capacity,enrolled,public,pop,radius]):raise ValueError('유한한 숫자가 필요합니다.')
    if count<0 or capacity<=0 or enrolled<0 or not 0<=public<=capacity or pop<=0 or radius<=0:raise ValueError('분모·수치 범위를 확인하세요.')
    density=count/(math.pi*radius**2);occ=enrolled/capacity;share=public/capacity
    clamp=lambda x:max(0,min(1,x))
    factors=[clamp(1-density),clamp((occ-.7)/.3),clamp((.4-share)/.4)]
    return {'cohort':r['cohort'],'reference_date':r['reference_date'],'capacity_per_1000_children':round(capacity/pop*1000,2),'weighted_occupancy_pct':round(occ*100,2),'public_capacity_pct':round(share*100,2),'exploratory_scores':{label:round(sum(a*b for a,b in zip(factors,weights))*100,2) for label,weights in [('40/40/20',[.4,.4,.2]),('50/30/20',[.5,.3,.2]),('30/50/20',[.3,.5,.2])]},'warning':'자체 탐구 지수. 시설 질·입소 가능성·부모 개인 상태의 판정값 아님.'}

if __name__=='__main__':
    with open(sys.argv[1],encoding='utf-8-sig') as f:
        print(json.dumps([compute(r) for r in csv.DictReader(f)],ensure_ascii=False,indent=2))
