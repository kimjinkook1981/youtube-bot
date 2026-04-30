import datetime
import json
import urllib.request
import re
from googleapiclient.discovery import build

YOUTUBE_API_KEY = "AIzaSyAG-wccTM37s3g1Qi05K0L0VxU098rziFg"

FIREBASE_URL_TREND = "https://workspace-f5b94-default-rtdb.firebaseio.com/trendData.json"
FIREBASE_URL_PARK = "https://workspace-f5b94-default-rtdb.firebaseio.com/parkData.json"
FIREBASE_URL_TIME = "https://workspace-f5b94-default-rtdb.firebaseio.com/updateTime.json" # 🔥 출근 도장용 주소 추가!

BLACKLIST = ["국방", "EBSDocumentary (EBS 다큐)", "뉴스", "윤택TV", "정치", "경제", "특보", "KBS", "MBC", "SBS", "YTN", "JTBC", "MBN", "채널A", "TV조선", "연합", "이슈", "신인균", "HaloFish", "HalFish"]

def parse_duration(duration_str):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return 0
    h, m, s = match.groups()
    return (int(h) if h else 0) * 3600 + (int(m) if m else 0) * 60 + (int(s) if s else 0)

# 1. 낚시 롱폼 트렌드 수집 함수
def get_channel_sum_trends(youtube):
    seven_days_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat() + "Z"
    print("🔍 1. 최근 대세 낚시 채널 발굴 중...")
    search_req = youtube.search().list(part="snippet", q="낚시", type="video", order="viewCount", publishedAfter=seven_days_ago, maxResults=50)
    search_res = search_req.execute()

    channel_ids = list(set([item['snippet']['channelId'] for item in search_res['items']]))
    print(f"📊 2. {len(channel_ids)}개 채널 중 불청객 걸러내고 합산 중...")
    
    channels_data = []
    blacklist_lower = [w.lower() for w in BLACKLIST]

    for ch_id in channel_ids:
        ch_v_req = youtube.search().list(part="snippet", channelId=ch_id, type="video", publishedAfter=seven_days_ago, maxResults=15)
        try: ch_v_res = ch_v_req.execute()
        except: continue

        video_ids = [v['id']['videoId'] for v in ch_v_res.get('items', [])]
        if not video_ids: continue

        stats_req = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(video_ids))
        stats_res = stats_req.execute()

        ch_title = ""
        total_views = 0
        video_count = 0
        top_video_id, top_video_title = "", ""
        max_v = -1

        for v in stats_res.get('items', []):
            duration = parse_duration(v['contentDetails']['duration'])
            title = v['snippet']['title']
            ch_name = v['snippet']['channelTitle']
            
            is_banned = any(word in title.lower() for word in blacklist_lower) or any(word in ch_name.lower() for word in blacklist_lower)
            if duration >= 600 and not is_banned: 
                views = int(v['statistics'].get('viewCount', 0))
                ch_title = ch_name
                total_views += views
                video_count += 1
                if views > max_v:
                    max_v = views
                    top_video_id, top_video_title = v['id'], title

        if video_count > 0 and not any(word in ch_title.lower() for word in blacklist_lower):
            # 🔥 HTML과 완벽 연동되도록 v_int와 v_count 살려둠! 제목에 [합산] 중복 제거!
            channels_data.append({
                "id": top_video_id, 
                "title": top_video_title, 
                "ch": ch_title, 
                "v_int": total_views, 
                "v": f"{total_views:,}",
                "v_count": video_count
            })

    channels_data.sort(key=lambda x: x['v_int'], reverse=True)
    return channels_data[:20]

# 2. 박과장TV 전용 데이터 수집 함수
def get_park_tv_data(youtube):
    print("🎥 3. 박과장TV 최신 영상 실시간 수집 중...")
    search_req = youtube.search().list(part="snippet", q="박과장TV", type="channel", maxResults=1)
    search_res = search_req.execute()
    if not search_res['items']: return []
    
    ch_id = search_res['items'][0]['id']['channelId']
    v_req = youtube.search().list(part="snippet", channelId=ch_id, order="date", type="video", maxResults=6)
    v_res = v_req.execute()
    
    video_ids = [item['id']['videoId'] for item in v_res.get('items', [])]
    if not video_ids: return []
    
    stats_req = youtube.videos().list(part="snippet,statistics", id=",".join(video_ids))
    stats_res = stats_req.execute()
    
    park_list = []
    for v in stats_res.get('items', []):
        views = int(v['statistics'].get('viewCount', 0))
        park_list.append({"title": v['snippet']['title'], "v_int": views, "v": f"{views:,}"})
    return park_list

try:
    youtube_svc = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    
    trends_data = get_channel_sum_trends(youtube_svc)
    park_data = get_park_tv_data(youtube_svc)
    
    # 🔥 한국 시간으로 예쁘게 포맷팅
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    time_str = kst_now.strftime("%m월 %d일 %H:%M 업데이트")
    
    print("☁️ 파이어베이스로 데이터 전송 중...")
    
    # 트렌드 전송
    req1 = urllib.request.Request(FIREBASE_URL_TREND, method="PUT")
    req1.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req1, data=json.dumps(trends_data).encode('utf-8'))
    
    # 박과장TV 전송
    req2 = urllib.request.Request(FIREBASE_URL_PARK, method="PUT")
    req2.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req2, data=json.dumps(park_data).encode('utf-8'))

    # 🔥 출근 도장(업데이트 시간) 전송!!!
    req3 = urllib.request.Request(FIREBASE_URL_TIME, method="PUT")
    req3.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req3, data=json.dumps({"time": time_str}).encode('utf-8'))
    
    print("✅ 트렌드, 박과장TV, 그리고 시간까지 실시간 업데이트 완료!")
except Exception as e:
    print(f"❌ 오류 발생: {e}")
