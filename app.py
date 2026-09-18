import os, json, sqlite3, uuid, math, time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ExifTags
import cv2
import numpy as np

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / 'uploads'; RESULTS = BASE / 'results'; DB = BASE / 'lunarmatch.db'
UPLOADS.mkdir(exist_ok=True); RESULTS.mkdir(exist_ok=True)
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init_db():
    c=db(); c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT NOT NULL, result_json TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));'''); c.commit(); c.close()
init_db()


def gps_decimal(v):
    try:
        if hasattr(v, 'numerator'): return float(v.numerator)/float(v.denominator)
        if isinstance(v, tuple): return sum(float(x.numerator)/float(x.denominator)/(60**i) for i,x in enumerate(v))
        if isinstance(v, (list,tuple)): return sum(float(x)/(60**i) for i,x in enumerate(v))
        return float(v)
    except Exception: return None

def read_metadata(path):
    out={'available':False,'latitude':None,'longitude':None,'altitude':None,'acquisition_time':None,'camera':None,'mission':None,'crs':None,'projection':None,'datum':None,'image_id':None,'source':'Embedded image metadata'}
    try:
        im=Image.open(path); ex=im.getexif(); tags={ExifTags.TAGS.get(k,k):v for k,v in ex.items()}
        out['camera']=tags.get('Model') or tags.get('Make')
        out['acquisition_time']=tags.get('DateTimeOriginal') or tags.get('DateTime')
        gps=tags.get('GPSInfo')
        if gps:
            gps2={ExifTags.GPSTAGS.get(k,k):v for k,v in gps.items()}
            lat=gps2.get('GPSLatitude'); lon=gps2.get('GPSLongitude')
            if lat and lon:
                out['latitude']=gps_decimal(lat)*( -1 if gps2.get('GPSLatitudeRef') in ['S','s'] else 1)
                out['longitude']=gps_decimal(lon)*( -1 if gps2.get('GPSLongitudeRef') in ['W','w'] else 1)
            alt=gps2.get('GPSAltitude')
            if alt: out['altitude']=gps_decimal(alt)
        # Optional sidecar is deliberately explicit: never infer coordinates.
        side=path.with_suffix('.json')
        if side.exists():
            data=json.loads(side.read_text())
            for k in out:
                if k in data and data[k] not in [None,'']: out[k]=data[k]
            out['source']='Embedded metadata + supplied reference metadata'
        out['available']=any(v is not None for k,v in out.items() if k not in ['available','source'])
    except Exception as e: out['metadata_error']=str(e)
    return out

def image_info(path):
    im=cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if im is None: raise ValueError('Unsupported or unreadable image.')
    h,w=im.shape
    return im,w,h

def analyze(a_path,b_path):
    t=time.perf_counter(); a,aw,ah=image_info(a_path); b,bw,bh=image_info(b_path)
    maxdim=1600
    def resize(x):
        h,w=x.shape; s=min(1.0,maxdim/max(h,w));
        return cv2.resize(x,(round(w*s),round(h*s))) if s<1 else x
    aa,bb=resize(a),resize(b)
    sift=cv2.SIFT_create(nfeatures=5000, contrastThreshold=0.02)
    ka,da=sift.detectAndCompute(aa,None); kb,db=sift.detectAndCompute(bb,None)
    raw=[]; reciprocal=[]
    if da is not None and db is not None and len(ka)>=2 and len(kb)>=2:
        bf=cv2.BFMatcher(cv2.NORM_L2)
        knn=bf.knnMatch(da,db,k=2)
        raw=[m for m,n in knn if m.distance < 0.72*n.distance]
        rev=bf.knnMatch(db,da,k=2); revbest={m.queryIdx:m.trainIdx for pair in rev if len(pair)==2 for m,n in [pair] if m.distance < 0.72*n.distance}
        reciprocal=[m for m in raw if revbest.get(m.trainIdx)==m.queryIdx]
    inliers=[]; H=None
    if len(reciprocal)>=4:
        src=np.float32([ka[m.queryIdx].pt for m in reciprocal]).reshape(-1,1,2); dst=np.float32([kb[m.trainIdx].pt for m in reciprocal]).reshape(-1,1,2)
        H,mask=cv2.findHomography(src,dst,cv2.RANSAC,5.0)
        if mask is not None: inliers=[i for i,x in enumerate(mask.ravel()) if x]
    verified=len(inliers); candidates=len(reciprocal); raw_n=len(raw)
    inlier_ratio=(verified/candidates*100) if candidates else 0
    coverage=(len({reciprocal[i].queryIdx for i in inliers})/max(1,len(ka))*100) if ka else 0
    consistency=min(100, inlier_ratio*0.7+min(100,coverage)*0.3)
    score=min(100, (verified/max(1,min(len(ka),len(kb)))*100)*0.45 + inlier_ratio*0.35 + consistency*0.20)
    label='HIGH' if score>=70 and verified>=8 else 'MODERATE' if score>=40 and verified>=5 else 'LOW' if verified else 'INSUFFICIENT'
    # visual correspondence
    draw=cv2.drawMatches(aa,ka,bb,kb, [reciprocal[i] for i in inliers], None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    rid=uuid.uuid4().hex; out=RESULTS/f'correspondence_{rid}.jpg'; cv2.imwrite(str(out),draw)
    ma=read_metadata(a_path); mb=read_metadata(b_path)
    return {'analysis_id':rid,'created_at':datetime.now(timezone.utc).isoformat(),'score':round(score,2),'reliability':label,'raw_matches':raw_n,'candidate_matches':candidates,'verified_matches':verified,'inlier_ratio':round(inlier_ratio,2),'feature_coverage':round(coverage,2),'geometric_consistency':round(consistency,2),'homography_status':'ESTABLISHED' if H is not None else 'NOT ESTABLISHED','processing_time_ms':round((time.perf_counter()-t)*1000,1),'algorithm':'SIFT + Lowe ratio test + reciprocal matching + RANSAC','image_a':{'width':aw,'height':ah,'keypoints':len(ka),'metadata':ma},'image_b':{'width':bw,'height':bh,'keypoints':len(kb),'metadata':mb},'result_image':f'/results/{out.name}','validation_note':'Score is a correspondence/reliability indicator, not ground-truth accuracy.'}

@app.context_processor
def globals(): return {'logged_in':bool(session.get('user_id')),'user_name':session.get('user_name')}

@app.route('/')
def home(): return render_template('home.html')
@app.route('/<page>')
def page(page):
    allowed={'analyze','results','validation','stress','technology','about','contact','signin','signup'}
    if page not in allowed: return render_template('404.html'),404
    return render_template(page+'.html')
@app.post('/api/signup')
def signup():
    d=request.get_json() or {}; name=d.get('name','').strip(); email=d.get('email','').strip().lower(); pw=d.get('password','')
    if not name or not email or len(pw)<8: return jsonify(error='Name, email and a password of at least 8 characters are required.'),400
    try:
        c=db(); c.execute('INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)',(name,email,generate_password_hash(pw),datetime.now(timezone.utc).isoformat())); c.commit(); uid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; c.close()
        session['user_id']=uid; session['user_name']=name; return jsonify(ok=True)
    except sqlite3.IntegrityError: return jsonify(error='An account with that email already exists.'),409
@app.post('/api/signin')
def signin():
    d=request.get_json() or {}; c=db(); u=c.execute('SELECT * FROM users WHERE email=?',(d.get('email','').strip().lower(),)).fetchone(); c.close()
    if not u or not check_password_hash(u['password'],d.get('password','')): return jsonify(error='Invalid email or password.'),401
    session['user_id']=u['id']; session['user_name']=u['name']; return jsonify(ok=True)
@app.post('/api/signout')
def signout(): session.clear(); return jsonify(ok=True)
@app.post('/api/analyze')
def api_analyze():
    if 'image_a' not in request.files or 'image_b' not in request.files: return jsonify(error='Upload Image A and Image B.'),400
    a=request.files['image_a']; b=request.files['image_b']; aid=uuid.uuid4().hex; ap=UPLOADS/f'{aid}_a{Path(a.filename).suffix.lower()}'; bp=UPLOADS/f'{aid}_b{Path(b.filename).suffix.lower()}'; a.save(ap); b.save(bp)
    try: result=analyze(ap,bp)
    except Exception as e: return jsonify(error=str(e)),422
    c=db(); c.execute('INSERT INTO analyses(id,user_id,created_at,result_json) VALUES(?,?,?,?)',(result['analysis_id'],session.get('user_id'),result['created_at'],json.dumps(result))); c.commit(); c.close(); return jsonify(result)
@app.get('/api/results')
def api_results():
    c=db(); rows=c.execute('SELECT id,created_at,result_json FROM analyses WHERE user_id=? OR user_id IS NULL ORDER BY created_at DESC LIMIT 30',(session.get('user_id'),)).fetchall(); c.close(); return jsonify([json.loads(r['result_json']) for r in rows])
@app.get('/api/health')
def health(): return jsonify(status='online',service='LUNARMATCH V2',engine='Python OpenCV SIFT + BFMatcher + RANSAC',validation='metadata-aware; no coordinate fabrication')
@app.route('/results/<path:name>')
def result_file(name): return send_from_directory(RESULTS,name)
@app.errorhandler(413)
def too_large(e): return jsonify(error='Maximum upload size is 25 MB.'),413

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
