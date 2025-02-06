import json
import requests
import urllib.parse
import time
import datetime
import random
import os
import subprocess
import ast

from cache import cache
import yt_dlp

# --- 共通設定・定数 ---
# APIのタイムアウト設定（InvidiousAPI用）
max_api_wait_time = (1.5, 1)  # (connect, read) のタイムアウト
max_time = 10

# クッキー判定用（両コード共通）
def checkCookie(cookie: str) -> bool:
    return cookie == "True"

# User-Agent をランダムに選ぶ関数
user_agents = [
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3864.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:62.0) Gecko/20100101 Firefox/62.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:67.0) Gecko/20100101 Firefox/67.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:68.0) Gecko/20100101 Firefox/68.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:61.0) Gecko/20100101 Firefox/61.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36 Edg/94.0.992.31',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Safari/605.1.15',
  'Mozilla/5.0 (iPhone; CPU iPhone OS 12_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1'
]

def getRandomUserAgent():
    ua = random.choice(user_agents)
    print("User-Agent:", ua)
    return {'User-Agent': ua}

# --- Invidious API クラス（yuyuyu-new-instance 側の実装を採用） ---
class InvidiousAPI:
    def __init__(self):
        # 外部リポジトリから Invidious インスタンスリストを取得
        self.all = ast.literal_eval(requests.get(
            'https://raw.githubusercontent.com/LunaKamituki/yukiyoutube-inv-instances/refs/heads/main/main.txt',
            headers=getRandomUserAgent(),
            timeout=(1.0, 0.5)
        ).text)
        
        self.video    = self.all['video']
        self.playlist = self.all['playlist']
        self.search   = self.all['search']
        self.channel  = self.all['channel']
        self.comments = self.all['comments']

        # 動画の実際の有無をチェックするか
        self.check_video = False

    def info(self):
        return {
            'API': self.all,
            'checkVideo': self.check_video
        }

# グローバル変数として InvidiousAPI インスタンスを作成
invidious_api = InvidiousAPI()

# 外部BBSサーバURL（各種掲示板関連 API で利用）
url = requests.get('https://raw.githubusercontent.com/LunaKamituki/Yuki-BBS-Server-URL/refs/heads/main/server.txt',
                   headers=getRandomUserAgent()).text.rstrip()

version = "1.0"
new_instance_version = "1.3.2"

# UNIX系の場合、実行権限を付与（bbs用の実行ファイル）
os.system("chmod 777 ./yukiverify")

# --- 例外定義 ---
class APITimeoutError(Exception):
    pass

class UnallowedBot(Exception):
    pass

# --- 共通ユーティリティ ---
def isJSON(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

def updateList(api_list, api):
    api_list.append(api)
    api_list.remove(api)
    return api_list

def requestAPI(path, api_urls):
    starttime = time.time()
    
    for api in api_urls:
        if time.time() - starttime >= max_time - 1:
            break
        try:
            full_url = api + 'api/v1' + path
            print("Requesting:", full_url)
            res = requests.get(full_url, headers=getRandomUserAgent(), timeout=max_api_wait_time)
            if res.status_code == requests.codes.ok and isJSON(res.text):
                # 動画の場合、追加チェック（必要に応じて）
                if invidious_api.check_video and path.startswith('/video/'):
                    video_url = json.loads(res.text)['formatStreams'][0]['url']
                    video_res = requests.get(video_url, headers=getRandomUserAgent(), timeout=(3.0, 0.5))
                    if 'video' not in video_res.headers.get('Content-Type', ''):
                        print(f"No Video (Content-Type: {video_res.headers.get('Content-Type','')}): {api}")
                        updateList(api_urls, api)
                        continue
                # チャンネルの場合、直近動画が空の場合はスキップ
                if path.startswith('/channel/') and json.loads(res.text).get("latestvideo", []) == []:
                    print(f"No Channel: {api}")
                    updateList(api_urls, api)
                    continue

                print(f"Success ({path.split('/')[1].split('?')[0]}): {api}")
                return res.text
            elif isJSON(res.text):
                err = json.loads(res.text).get('error', '')
                print(f"Returned Error (JSON): {api} ('{err}')")
                updateList(api_urls, api)
            else:
                print(f"Returned Error: {api} ('{res.text[:100]}')")
                updateList(api_urls, api)
        except Exception as e:
            print(f"Exception: {api} ({e})")
            updateList(api_urls, api)
    
    raise APITimeoutError("APIがタイムアウトしました")

def getInfo(request):
    # リクエスト情報などをJSONにして返す（BBS等で利用）
    return json.dumps([
        version,
        os.environ.get('RENDER_EXTERNAL_URL'),
        str(request.scope["headers"]),
        str(request.scope['router'])[39:-2]
    ])

failed = "Load Failed"

# --- 動画・検索・チャンネル・プレイリスト・コメント取得関数 ---
def getVideoData(videoid):
    # Invidious API 経由で動画情報を取得
    t = json.loads(requestAPI(f"/videos/{urllib.parse.quote(videoid)}", invidious_api.video))
    if 'recommendedvideo' in t:
        recommended_videos = t["recommendedvideo"]
    elif 'recommendedVideos' in t:
        recommended_videos = t["recommendedVideos"]
    else:
        recommended_videos = [{
            "videoId": failed,
            "title": failed,
            "authorId": failed,
            "author": failed,
            "lengthSeconds": 0,
            "viewCountText": "Load Failed"
        }]
    return [
        {
            'video_urls': list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
            'description_html': t["descriptionHtml"].replace("\n", "<br>"),
            'title': t["title"],
            'length_text': str(datetime.timedelta(seconds=t["lengthSeconds"])),
            'author_id': t["authorId"],
            'author': t["author"],
            'author_thumbnails_url': t["authorThumbnails"][-1]["url"],
            'view_count': t.get("viewCount", "0"),
            'like_count': t.get("likeCount", "0"),
            'subscribers_count': t.get("subCountText", "0")
        },
        [
            {
                "video_id": i["videoId"],
                "title": i["title"],
                "author_id": i["authorId"],
                "author": i["author"],
                "length_text": str(datetime.timedelta(seconds=i["lengthSeconds"])),
                "view_count_text": i["viewCountText"]
            } for i in recommended_videos
        ]
    ]

def getSearchData(q, page):
    def formatSearchData(data_dict):
        if data_dict["type"] == "video":
            return {
                "type": "video",
                "title": data_dict.get("title", failed),
                "id": data_dict.get("videoId", failed),
                "authorId": data_dict.get("authorId", failed),
                "author": data_dict.get("author", failed),
                "published": data_dict.get("publishedText", failed),
                "length": str(datetime.timedelta(seconds=data_dict.get("lengthSeconds", 0))),
                "view_count_text": data_dict.get("viewCountText", "")
            }
        elif data_dict["type"] == "playlist":
            return {
                "type": "playlist",
                "title": data_dict.get("title", failed),
                "id": data_dict.get("playlistId", failed),
                "thumbnail": data_dict.get("playlistThumbnail", failed),
                "count": data_dict.get("videoCount", failed)
            }
        # チャンネル
        else:
            # authorThumbnails の先頭が https かどうかで判定
            thumb = (data_dict["authorThumbnails"][-1]["url"]
                     if 'authorThumbnails' in data_dict and len(data_dict["authorThumbnails"]) > 0
                     else failed)
            return {
                "type": "channel",
                "author": data_dict.get("author", failed),
                "id": data_dict.get("authorId", failed),
                "thumbnail": thumb
            }
    datas_dict = json.loads(requestAPI(f"/search?q={urllib.parse.quote(q)}&page={page}&hl=jp", invidious_api.search))
    return [formatSearchData(data_dict) for data_dict in datas_dict]

def getChannelData(channelid):
    t = json.loads(requestAPI(f"/channels/{urllib.parse.quote(channelid)}", invidious_api.channel))
    if 'latestvideo' in t:
        latest_videos = t['latestvideo']
    elif 'latestVideos' in t:
        latest_videos = t['latestVideos']
    else:
        latest_videos = [{
            "title": failed,
            "videoId": failed,
            "authorId": failed,
            "author": failed,
            "publishedText": failed,
            "viewCountText": "0",
            "lengthSeconds": 0
        }]
    return [
        [
            {
                "type": "video",
                "title": i["title"],
                "id": i["videoId"],
                "authorId": t["authorId"],
                "author": t["author"],
                "published": i["publishedText"],
                "view_count_text": i.get('viewCountText', ""),
                "length_str": str(datetime.timedelta(seconds=i["lengthSeconds"]))
            } for i in latest_videos
        ],
        {
            "channel_name": t["author"],
            "channel_icon": t["authorThumbnails"][-1]["url"],
            "channel_profile": t["descriptionHtml"],
            "author_banner": (urllib.parse.quote(t["authorBanners"][0]["url"], safe="-_.~/:")
                              if 'authorBanners' in t and len(t['authorBanners']) > 0 else ''),
            "subscribers_count": t.get("subCount", "0"),
            "tags": t.get("tags", [])
        }
    ]

def getPlaylistData(listid, page):
    t = json.loads(requestAPI(f"/playlists/{urllib.parse.quote(listid)}?page={urllib.parse.quote(page)}", invidious_api.playlist))["videos"]
    return [{"title": i["title"], "id": i["videoId"], "authorId": i["authorId"], "author": i["author"], "type": "video"} for i in t]

def getCommentsData(videoid):
    t = json.loads(requestAPI(f"/comments/{urllib.parse.quote(videoid)}?hl=jp", invidious_api.comments))["comments"]
    return [{"author": i["author"],
             "authoricon": i["authorThumbnails"][-1]["url"],
             "authorid": i["authorId"],
             "body": i["contentHtml"].replace("\n", "<br>")}
            for i in t]

# BBS や認証関連で利用する外部ソースの取得
@cache(seconds=120)
def getSource(name):
    return requests.get(f'https://raw.githubusercontent.com/shiratama-kotone/yuki-source/refs/heads/main/{name}.html',
                        headers=getRandomUserAgent()).text

# BBS用の検証コード取得
def getVerifyCode():
    try:
        result = subprocess.run(["./yukiverify"], encoding='utf-8', stdout=subprocess.PIPE)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"getVerifyCode Error: {e}")
        return None

# --- FastAPI アプリ設定 ---
from fastapi import FastAPI, Depends, Response, Cookie, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse as redirect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Union

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
# 静的ファイルのマウント（両コードのディレクトリ構造を統合）
app.mount("/js", StaticFiles(directory="./statics/js"), name="js")
app.mount("/css", StaticFiles(directory="./statics/css"), name="css")
app.mount("/img", StaticFiles(directory="./statics/img"), name="img")
app.mount("/genesis", StaticFiles(directory="./blog", html=True), name="blog")
app.add_middleware(GZipMiddleware, minimum_size=1000)
template = Jinja2Templates(directory='templates').TemplateResponse

no_robot_meta_tag = '<meta name="robots" content="noindex,nofollow">'

# --- 各エンドポイント ---
@app.get("/", response_class=HTMLResponse)
def home(response: Response, request: Request, yuki: Union[str, None] = Cookie(None)):
    if checkCookie(yuki):
        response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
        return template("home.html", {"request": request})
    return redirect("/genesis")

@app.get('/watch', response_class=HTMLResponse)
def video(v: str, response: Response, request: Request, yuki: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    video_data = getVideoData(v)
    return template('video.html', {
        "request": request,
        "videoid": v,
        "videourls": video_data[0]['video_urls'],
        "description": video_data[0]['description_html'],
        "video_title": video_data[0]['title'],
        "author_id": video_data[0]['author_id'],
        "author_icon": video_data[0]['author_thumbnails_url'],
        "author": video_data[0]['author'],
        "length_text": video_data[0]['length_text'],
        "view_count": video_data[0]['view_count'],
        "like_count": video_data[0]['like_count'],
        "subscribers_count": video_data[0]['subscribers_count'],
        "recommended_videos": video_data[1],
        "proxy": proxy
    })

@app.get("/search", response_class=HTMLResponse)
def search(q: str, response: Response, request: Request, page: Union[int, None] = 1, yuki: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    results = getSearchData(q, page)
    return template("search.html", {
        "request": request,
        "results": results,
        "word": q,
        "next": f"/search?q={q}&page={page + 1}",
        "proxy": proxy
    })

@app.get("/hashtag/{tag}")
def hashtag(tag: str, response: Response, request: Request, page: Union[int, None] = 1, yuki: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    return redirect(f"/search?q={tag}")

@app.get("/channel/{channelid}", response_class=HTMLResponse)
def channel(channelid: str, response: Response, request: Request, yuki: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    ch_data = getChannelData(channelid)
    return template("channel.html", {
        "request": request,
        "results": ch_data[0],
        "channel_name": ch_data[1]["channel_name"],
        "channel_icon": ch_data[1]["channel_icon"],
        "channel_profile": ch_data[1]["channel_profile"],
        "cover_img_url": ch_data[1].get("author_banner", ""),
        "subscribers_count": ch_data[1].get("subscribers_count", "0"),
        "proxy": proxy
    })

@app.get("/playlist", response_class=HTMLResponse)
def playlist(list: str, response: Response, request: Request, page: Union[int, None] = 1, yuki: Union[str, None] = Cookie(None), proxy: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    results = getPlaylistData(list, str(page))
    return template("search.html", {
        "request": request,
        "results": results,
        "word": "",
        "next": f"/playlist?list={list}",
        "proxy": proxy
    })

@app.get("/comments")
def comments(request: Request, v: str):
    return template("comments.html", {"request": request, "comments": getCommentsData(v)})

@app.get("/thumbnail")
def thumbnail(v: str):
    thumb = requests.get(f"https://img.youtube.com/vi/{v}/0.jpg").content
    return Response(content=thumb, media_type="image/jpeg")

@app.get("/suggest")
def suggest(keyword: str):
    # Googleの補完APIを利用してサジェスト取得
    q = urllib.parse.quote(keyword)
    url_suggest = f"http://www.google.com/complete/search?client=youtube&hl=ja&ds=yt&q={q}"
    res = requests.get(url_suggest, headers=getRandomUserAgent())
    # 結果は "[keyword, [[suggestion, ...], ...]]" の形式
    data = json.loads(res.text[19:-1])
    return [i[0] for i in data[1]]

# --- BBS 関連 ---
@app.get("/bbs", response_class=HTMLResponse)
def bbs(request: Request, name: Union[str, None] = "", seed: Union[str, None] = "", channel: Union[str, None] = "main", verify: Union[str, None] = "false", yuki: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    bbs_html = requests.get(
        f"{url}bbs?name={urllib.parse.quote(name)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}",
        cookies={"yuki": "True"}
    ).text
    # noindex設定と外部ソースのHTMLを付加
    res = HTMLResponse(no_robot_meta_tag + bbs_html.replace('AutoLink(xhr.responseText);', 'urlConvertToLink(xhr.responseText);') + getSource('bbs'))
    return res

@cache(seconds=5)
def getCachedBBSAPI(verify, channel):
    return requests.get(
        f"{url}bbs/api?t={urllib.parse.quote(str(int(time.time()*1000)))}&verify={urllib.parse.quote(verify)}&channel={urllib.parse.quote(channel)}",
        cookies={"yuki": "True"}
    ).text

@app.get("/bbs/api", response_class=HTMLResponse)
def bbsAPI(request: Request, t: str, channel: Union[str, None] = "main", verify: Union[str, None] = "false"):
    return getCachedBBSAPI(verify, channel)

@app.get("/bbs/result")
def write_bbs(request: Request, name: str = "", message: str = "", seed: Union[str, None] = "", channel: Union[str, None] = "main", verify: Union[str, None] = "false", yuki: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    result = requests.get(
        f"{url}bbs/result?name={urllib.parse.quote(name)}&message={urllib.parse.quote(message)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}&info={urllib.parse.quote(getInfo(request))}&serververify={getVerifyCode()}",
        cookies={"yuki": "True"},
        allow_redirects=False
    )
    if result.status_code != 307:
        return HTMLResponse(no_robot_meta_tag + result.text.replace('AutoLink(xhr.responseText);', 'urlConvertToLink(xhr.responseText);') + getSource('bbs'))
    return redirect(f"/bbs?name={urllib.parse.quote(name)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}")

@cache(seconds=120)
def getCachedBBSHow():
    return requests.get(f"{url}bbs/how").text

@app.get("/bbs/how", response_class=PlainTextResponse)
def bbsHow(request: Request, yuki: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    return getCachedBBSHow()

@app.get("/verify", response_class=HTMLResponse)
def get_form(seed=""):
    return requests.get(f"{url}verify?seed={urllib.parse.quote(seed)}").text

@app.post("/submit", response_class=HTMLResponse)
def submit(h_captcha_response: str = Form(alias="h-captcha-response"), seed: str = Form(...)):
    return requests.post(f"{url}submit", data={"h-captcha-response": h_captcha_response, "seed": seed}).text

# --- その他の管理・API情報関連 ---
@app.get("/info", response_class=HTMLResponse)
def viewlist(response: Response, request: Request, yuki: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template("info.html", {
        "request": request,
        "Youtube_API": invidious_api.video[0],
        "Channel_API": invidious_api.channel[0],
        "comments": invidious_api.comments[0]
    })

# /reset エンドポイントでインスタンス等を再読み込み（/load_instance の代替）
@app.get("/reset", response_class=PlainTextResponse)
def reset():
    global url, invidious_api
    url = requests.get('https://raw.githubusercontent.com/mochidukiyukimi/yuki-youtube-instance/refs/heads/main/instance.txt',
                       headers=getRandomUserAgent()).text.rstrip()
    invidious_api = InvidiousAPI()
    return 'Success'

@app.get("/version", response_class=PlainTextResponse)
def displayVersion():
    return str({'version': version, 'new_instance_version': new_instance_version})

@app.get("/api/update", response_class=PlainTextResponse)
def updateAllAPI():
    global invidious_api
    invidious_api = InvidiousAPI()
    return str(invidious_api.info())

@app.get("/api/{api_name}", response_class=PlainTextResponse)
def displayAPI(api_name: str):
    match api_name:
        case 'all':
            api_value = invidious_api.info()
        case 'video':
            api_value = invidious_api.video
        case 'search':
            api_value = invidious_api.search
        case 'channel':
            api_value = invidious_api.channel
        case 'comments':
            api_value = invidious_api.comments
        case 'playlist':
            api_value = invidious_api.playlist
        case _:
            api_value = f'API Name Error: {api_name}'
    return str(api_value)

@app.get("/api/{api_name}/next", response_class=PlainTextResponse)
def rotateAPI(api_name: str):
    match api_name:
        case 'video':
            updateList(invidious_api.video, invidious_api.video[0])
        case 'search':
            updateList(invidious_api.search, invidious_api.search[0])
        case 'channel':
            updateList(invidious_api.channel, invidious_api.channel[0])
        case 'comments':
            updateList(invidious_api.comments, invidious_api.comments[0])
        case 'playlist':
            updateList(invidious_api.playlist, invidious_api.playlist[0])
        case _:
            return f'API Name Error: {api_name}'
    return 'Finish'

@app.get("/api/video/check", response_class=PlainTextResponse)
def displayCheckVideo():
    return str(invidious_api.check_video)

@app.get("/api/video/check/toggle", response_class=PlainTextResponse)
def toggleVideoCheck():
    global invidious_api
    invidious_api.check_video = not invidious_api.check_video
    return f'{not invidious_api.check_video} to {invidious_api.check_video}'

# --- エラーハンドラ ---
@app.exception_handler(500)
def error500(request: Request, __):
    return template("error.html", {"request": request, "context": '500 Internal Server Error'}, status_code=500)

@app.exception_handler(APITimeoutError)
def apiTimeout(request: Request, exception: APITimeoutError):
    return template("apiTimeout.html", {"request": request}, status_code=504)

@app.exception_handler(UnallowedBot)
def unallowedBot(request: Request, exception: UnallowedBot):
    return template("error.html", {"request": request, "context": '403 Forbidden'}, status_code=403)
