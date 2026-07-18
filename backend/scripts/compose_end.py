from PIL import Image, ImageDraw, ImageFont
import numpy as np
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
base   = _root / 'res' / 'host' / 'crayon'
ico_dir = _root / 'res' / 'ico'

W, H = 1312, 736

zhao = Image.open(base / 'zhao_circle.png')
can  = Image.open(base / 'can_circle.png')

def crop_content(img):
    a = np.array(img)[:,:,3]; m = a>10
    r = np.any(m,1); c = np.any(m,0)
    return img.crop((np.where(c)[0][0], np.where(r)[0][0],
                     np.where(c)[0][-1]+1, np.where(r)[0][-1]+1))

zhao_c = crop_content(zhao); can_c = crop_content(can)

char_zone = int(H * 0.65)
can_top   = int(H * 0.15)
can_h = char_zone - can_top
can_s = can_c.resize((can_h, can_h), Image.LANCZOS)
zhao_h = int(can_h * 0.9)
zhao_s = zhao_c.resize((zhao_h, zhao_h), Image.LANCZOS)

canvas = Image.new('RGBA', (W,H), (8,8,12,255))
draw = ImageDraw.Draw(canvas)

gap = 2
total_w = zhao_s.width + can_s.width + gap
start_x = (W - total_w)//2
zhao_x, zhao_y = start_x, can_top + (can_h - zhao_h)
can_x,  can_y  = start_x + zhao_s.width + gap, can_top

canvas.paste(zhao_s, (zhao_x, zhao_y), zhao_s)
canvas.paste(can_s,  (can_x,  can_y),  can_s)

# Icons: icon_4=点赞, icon_3=投币, icon_1=收藏
icon_files = {'like': 'icon_4.png', 'coin': 'icon_3.png', 'save': 'icon_1.png'}
labels     = {'like': '点赞',      'coin': '投币',      'save': '收藏'}
order      = ['like', 'coin', 'save']

icons = {}
ico_h_target = 90
for name in order:
    ico = Image.open(ico_dir / icon_files[name]).convert('RGBA')
    tw = int(ico_h_target * ico.width / ico.height)
    icons[name] = ico.resize((tw, ico_h_target), Image.LANCZOS)

font = ImageFont.truetype(str(_root / 'res' / 'font' / 'SourceHanSansCN-Medium.otf'), 24)

ico_gap = 70
total_iw = sum(icons[n].width for n in order) + ico_gap*(len(order)-1)
ico_start_x = (W - total_iw)//2
btn_zone = H - char_zone
ico_y = char_zone + (btn_zone - ico_h_target)//2 - 30

curr_x = ico_start_x
for name in order:
    ico = icons[name]
    canvas.paste(ico, (curr_x, ico_y), ico)
    bbox = draw.textbbox((0,0), labels[name], font=font)
    tw = bbox[2]-bbox[0]
    lx = curr_x + (ico.width - tw)//2
    draw.text((lx, ico_y+ico_h_target+8), labels[name], font=font, fill=(210,190,200,255))
    curr_x += ico.width + ico_gap

out = base / 'end.png'
canvas.save(out)
print(f'Saved: {out}  ({W}x{H})')
