"""
PNG 아이콘 생성 스크립트 (외부 라이브러리 불필요)
농구공 느낌의 아이콘: 파란 배경 + 흰 원 + 주황 농구공 라인
"""
import struct, zlib, math

BG   = (37, 99, 235)    # blue-600
FG   = (255, 255, 255)  # white
ORG  = (251, 146, 60)   # orange-400 (농구공 라인)


def lerp(a, b, t):
    return a + (b - a) * t


def blend(fg, bg, alpha):
    return tuple(int(lerp(bg[i], fg[i], alpha)) for i in range(3))


def make_icon_png(size: int) -> bytes:
    half = size / 2
    radius = half * 0.72          # 흰 원 반지름
    ball_r  = half * 0.68         # 농구공 라인 반지름
    line_w  = size * 0.04         # 라인 굵기

    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            cx = x - half + 0.5
            cy = y - half + 0.5
            dist = math.sqrt(cx*cx + cy*cy)

            # 안티앨리어싱 헬퍼
            def aa(edge, w=1.2):
                return max(0.0, min(1.0, (edge - dist) / w))

            # 배경 파랑
            pixel = list(BG)

            # 흰 원 내부
            alpha_circle = aa(radius)
            if alpha_circle > 0:
                pixel = list(blend(FG, tuple(pixel), alpha_circle))

                # 농구공 호선들 (주황)
                # 수직 선
                dist_v = abs(cx)
                dist_h = abs(cy)

                # 세로 중앙선
                if dist < ball_r:
                    seg_v = aa(line_w / 2, 0.8) if (dist < ball_r) else 0
                    on_v = max(0.0, min(1.0, (line_w/2 - abs(cx)) / 1.0))
                    # 가로 중앙선
                    on_h = max(0.0, min(1.0, (line_w/2 - abs(cy)) / 1.0))
                    # 위쪽 곡선 (원호 느낌)
                    arc_y1 = -half * 0.3
                    arc_r1 = half * 0.5
                    da1 = abs(math.sqrt(cx*cx + (cy - arc_y1)**2) - arc_r1)
                    on_a1 = max(0.0, min(1.0, (line_w/2 - da1) / 1.0))
                    arc_y2 = half * 0.3
                    da2 = abs(math.sqrt(cx*cx + (cy - arc_y2)**2) - arc_r1)
                    on_a2 = max(0.0, min(1.0, (line_w/2 - da2) / 1.0))

                    line_alpha = max(on_v, on_h, on_a1, on_a2)
                    if line_alpha > 0:
                        pixel = list(blend(ORG, tuple(pixel), line_alpha * 0.85))

                # 원 테두리 (주황)
                edge_a = max(0.0, min(1.0, (line_w/2 - abs(dist - ball_r)) / 1.0))
                if edge_a > 0:
                    pixel = list(blend(ORG, tuple(pixel), edge_a * 0.85))

            row.extend(pixel)
        pixels.append(row)

    # PNG 인코딩
    raw = b''
    for row in pixels:
        raw += b'\x00' + bytes(row)
    compressed = zlib.compress(raw, 9)

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'IDAT', compressed)
        + chunk(b'IEND', b'')
    )


if __name__ == '__main__':
    import os
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'public')
    for size in (192, 512):
        path = os.path.join(out_dir, f'icon-{size}.png')
        data = make_icon_png(size)
        with open(path, 'wb') as f:
            f.write(data)
        print(f'[OK] {path} ({len(data):,} bytes)')
