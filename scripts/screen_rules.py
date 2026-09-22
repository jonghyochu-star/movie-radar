"""Explainable first-pass filters. No AI calls; never infer a film's production country.
Labels describe metadata evidence, not a verified movie or detected speech language.
The title-script fallback groups scripts rather than asserting a nationality.
"""
from __future__ import annotations
import re
import unicodedata

LANGS = {'en','ja','es','pt','fr','de','it','zh','vi','th','id','ru','tr','hi','ar','fa','ur','bn','ta','te','ko'}

def language_base(value):
    if not isinstance(value, str):
        return ''
    part = value.lower().replace('_','-').split('-')[0]
    return part if part in LANGS else ('other' if re.fullmatch(r'[a-z]{2,3}',part) else '')

def _title_language(snippet):
    """Text-only clues. Never call a Latin-script title English by default.

    defaultLanguage may refine an ambiguous script, but is not independent
    evidence that the spoken language, or even the title text, is correct.
    Film names, hashtags and boilerplate movie/scene words are not enough.
    """
    title = str(snippet.get('title',''))[:300]
    clean = re.sub(r'https?://\S+|#[\w]+', ' ', title)
    declared = language_base(snippet.get('defaultLanguage'))
    patterns = [
        ('ko', r'[\uac00-\ud7a3]', '제목의 한글'),
        ('ja', r'[\u3040-\u30ff]', '제목의 일본어 문자'),
        ('ar-script', r'[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]', '제목의 아랍 문자권 · 세부 언어 미확정'),
        ('indic-script', r'[\u0900-\u0d7f]', '제목의 인도계 문자권 · 세부 언어 미확정'),
        ('th', r'[\u0e00-\u0e7f]', '제목의 태국어 문자'),
        ('cyrillic', r'[\u0400-\u04ff]', '제목의 키릴 문자권 · 세부 언어 미확정'),
        ('zh', r'[\u4e00-\u9fff]', '제목의 한자 · 중국어 추정'),
    ]
    counts=[(code,len(re.findall(pattern,clean)),why) for code,pattern,why in patterns]
    if any(code=='ja' and n>=2 for code,n,_ in counts):
        return 'ja', '제목의 일본어 문자 · 음성 미확인'
    code,n,why=sorted(counts,key=lambda x:x[1],reverse=True)[0]
    if n>=3:
        if code=='ar-script' and declared in {'ar','fa','ur'}:
            code,why=declared,'제목 문자와 제목 언어 설정'
        elif code=='indic-script' and declared in {'hi','bn','ta','te'}:
            code,why=declared,'제목 문자와 제목 언어 설정'
        elif code=='cyrillic' and declared=='ru':
            code,why='ru','제목 문자와 제목 언어 설정'
        elif code=='zh' and declared=='ja':
            code,why='ja','제목의 한자와 일본어 제목 설정'
        return code, why+' · 추정, 음성 미확인'
    folded=unicodedata.normalize('NFKC',clean).lower()
    words=set(re.findall(r"[a-zà-ÿ]+",folded))
    # Do not count movie, film, scene, shorts, viral, names or hashtags as English.
    lex={
        'en':{'the','this','that','with','her','his','she','he','was','they','but','when','father','daughter'},
        'es':{'película','escena','hija','hijo','porque','madre','padre','una','ella','pero'},
        'pt':{'filme','cena','filha','filho','mãe','não','você','ela','seu','uma'},
        'fr':{'scène','extrait','fille','mère','père','une','avec','dans','elle','mais'},
        'de':{'filmszene','vater','tochter','mutter','nicht','eine','der','das','und','mit'},
        'it':{'scena','figlia','figlio','perché','della','dalla','questo','dopo','lui','suo'},
    }
    scored=sorted(((len(words&v),k) for k,v in lex.items()),reverse=True)
    n,lang=scored[0]
    # English is especially overrepresented in mixed-language clip titles.
    english_grammar={'the','this','that','with','her','his','she','he','was','they','but','when'}
    enough=(n>=3 and len(words & english_grammar)>=2) if lang=='en' else n>=2
    if enough and n>scored[1][0]:
        return lang, '제목 문장 단서 · 추정, 음성 미확인'
    return 'unknown', '음성 설정 없음 · 제목 단서 부족; 제목·설명 언어 설정만으로 통과시키지 않음'


def infer_language(snippet):
    """Audio metadata first; explainable title estimate second; otherwise unknown.

    Both YouTube language fields are uploader metadata, not speech recognition.
    Keep original declaration separate and never infer production country.
    """
    title_code,title_basis=_title_language(snippet)
    audio=language_base(snippet.get('defaultAudioLanguage')) or 'unknown'
    declared=language_base(snippet.get('defaultLanguage')) or 'unknown'
    if audio!='unknown':
        code,basis,source=audio,'업로더의 기본 음성 언어 설정 · 실제 음성 자동 검증 아님','audio'
    elif title_code!='unknown':
        code,basis,source=title_code,title_basis,'title'
    else:
        code,basis,source='unknown',title_basis,'unknown'
    return {'code':code,'basis':basis,'audio':audio,'declared':declared,
            'source':source,'titleCode':title_code,'titleBasis':title_basis}

FILM_PATTERNS = [
    r'\b(?:movie|film)[\s_-]*(?:scene|clip)s?\b',
    r'\b(?:scene|clip)s?\s+(?:from|of)\s+(?:the\s+)?(?:movie|film)\b',
    r'\b(?:short|independent|indie)\s+film\b',
    r'\b(?:movie|film)\s*(?:name|title)?\s*[:：]\s*[^\s#]',
    r'\bescena(?:s)?\s+(?:(?:de|la|una)\s+){0,3}pel[ií]cula\b',
    r'\bcena(?:s)?\s+(?:(?:de|do|um|o)\s+){0,3}filme\b',
    r'\b(?:sc[eè]ne|extrait)(?:s)?\s+(?:(?:de|du|le|un)\s+){0,3}film\b',
    r'\bfilmszene\b', r'\bscena\s+(?:(?:di|del|un)\s+){0,3}film\b',
    r'映画.{0,10}(?:シーン|名場面|切り抜き)|(?:シーン|名場面).{0,10}映画',
    r'电影片段|電影片段|电影名场面|電影名場面',
    r'сцена\s+из\s+фильма',r'adegan\s+film',r'cảnh\s+phim',
    r'مشهد\s+من\s+فيلم',r'फिल्म.{0,10}दृश्य',
]
TV_PATTERNS=[r'\b(?:tv|television)\s+(?:series|show|scene|clip)\b',
    r'\b(?:series|sitcom|episode)\s*(?:scene|clip|name|title|[:：])',
    r'ドラマ.{0,8}(?:シーン|切り抜き)|电视剧片段|電視劇片段',
    r'\b(?:escena|cena|sc[eè]ne)\s+(?:(?:de|da|du|la)\s+){0,3}s[eé]rie\b']
STRONG_NEGATIVE=[
 (r'\b(?:official\s+music\s+video|lyric(?:s)?\s+video|dance\s+challenge)\b','뮤직비디오·가사·댄스 챌린지 단서'),
 (r'\b(?:minecraft|roblox|fortnite|pubg|gameplay|free\s+fire|gta\s*[v56])\b','게임 플레이 단서'),
 (r'\b(?:prank|vlog|unboxing|makeup\s+tutorial|cooking\s+recipe|soccer\s+highlights|football\s+highlights)\b','브이로그·장난·생활·스포츠 단서'),
 (r'\b(?:pegadinha|broma|receta|maquillaje)\b|먹방|몰래카메라|게임플레이','생활·장난 콘텐츠 단서'),
 (r'\b(?:(?:actor|director|cast|celebrity)\s+interview|interview\s+with|podcast|movie\s+review|film\s+review|reaction\s+video)\b','인터뷰·리뷰·팟캐스트 단서'),
 (r'\b(?:camera\s+(?:review|rig|lens|gear)|lens\s+review|gimbal\s+review|microphone\s+review|filmmaking\s+gear)\b','촬영 장비·제품 단서'),
 (r'\b(?:official\s+trailer|teaser\s+trailer)\b|공식\s*예고편','예고편 단서 · 장면 편집과 구분'),
]

def screen_evidence(video):
    s=video.get('snippet',{})
    title=unicodedata.normalize('NFKC',str(s.get('title',''))).lower()
    # Do not let a long boilerplate/tag dump count as a movie identification.
    desc=unicodedata.normalize('NFKC',str(s.get('description',''))[:1600]).lower()
    prose=title+'\n'+re.sub(r'#[\w]+',' ',desc)
    meaningful_title=re.sub(r'#[\w]+',' ',title)
    tags=' '.join(str(x).lower() for x in (s.get('tags') or [])[:30] if isinstance(x,str))
    strong=next((p for p in FILM_PATTERNS if re.search(p,prose,re.I)),None)
    tv=next((p for p in TV_PATTERNS if re.search(p,prose,re.I)),None)
    negative=next((reason for pattern,reason in STRONG_NEGATIVE if re.search(pattern,title,re.I)),None)
    if negative:
        return {'kind':'non_screen','reason':negative+' · 규칙 기반, 오탐 가능'}
    if strong:
        match=re.search(strong,prose,re.I)
        where='제목' if re.search(strong,title,re.I) else '설명'
        phrase=match.group(0)[:80] if match else ''
        return {'kind':'film','reason':f'{where}의 〈{phrase}〉 문구 · 영화 단서일 뿐, 원작·감동결 미검증'}
    if tv:
        match=re.search(tv,prose,re.I)
        where='제목' if re.search(tv,title,re.I) else '설명'
        phrase=match.group(0)[:80] if match else ''
        return {'kind':'series','reason':f'{where}의 〈{phrase}〉 문구 · 드라마 단서일 뿐, 원작·감동결 미검증'}
    # Two independent weaker clues, not a single #movie tag or search keyword.
    narrative_film=bool(re.search(r'\b(?:movie|film|pel[ií]cula|filme)\b|映画|电影|電影',meaningful_title))
    tag_film=bool(re.search(r'\b(?:movie|film|cinema|movieclips|filmclips)\b',tags+' '+' '.join(re.findall(r'#[\w]+',title))))
    category=str(s.get('categoryId',''))
    topics=' '.join(str(x) for x in video.get('topicDetails',{}).get('topicCategories',[]))
    film_topic=bool(re.search(r'/(?:Film|Cinema)(?:$|[ _/])',topics,re.I))
    if (narrative_film and (tag_film or category=='1')) or (film_topic and tag_film):
        return {'kind':'film','reason':'영화 관련 제목/태그와 분류 단서 · 원작 미검증'}
    if category in {'10','15','17','20','25','26'}:
        return {'kind':'non_screen','reason':'음악·동물·스포츠·게임·뉴스·생활 분류이며 영화 장면 근거 부족'}
    return {'kind':'unknown','reason':'영화·드라마 장면이라고 판단할 단서 부족 · 숨김 조건 해제 시 검토 가능'}
