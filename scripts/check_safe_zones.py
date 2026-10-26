"""인스타 UI 가 덮는 영역(대략)을 빨갛게 칠해 겹침을 확인한다.

사용: python scripts/check_safe_zones.py feed|story|reel 입력.jpg 출력.jpg  (릴스는 ffmpeg 로 프레임을 뽑아서)
"""
import sys
from PIL import Image, ImageDraw
ZONES = {
    # 4:5 피드: 장수 표시(오른쪽 위), 영상 음소거 버튼(오른쪽 아래), 사람 태그(왼쪽 아래), 프로필 격자 3:4 잘림(좌우 34px)
    "feed": [(940, 24, 1056, 84), (980, 1250, 1056, 1326), (24, 1250, 100, 1326), (0, 0, 34, 1350), (1046, 0, 1080, 1350)],
    # 스토리: 진행 막대·프로필(위 250), 답장 칸(아래 300)
    "story": [(0, 0, 1080, 250), (0, 1620, 1080, 1920)],
    # 릴스: 위 250, 아래 520(아이디·캡션·음악), y 900 아래 오른쪽 아이콘 열
    "reel": [(0, 0, 1080, 250), (0, 1400, 1080, 1920), (920, 900, 1080, 1920)],
}
kind, src, dst = sys.argv[1:4]
im = Image.open(src).convert("RGBA")
ov = Image.new("RGBA", im.size)
d = ImageDraw.Draw(ov)
for z in ZONES[kind]:
    d.rectangle(z, fill=(255, 0, 60, 110), outline=(255, 0, 60, 255), width=3)
Image.alpha_composite(im, ov).convert("RGB").resize((im.width // 2, im.height // 2)).save(dst, quality=85)
