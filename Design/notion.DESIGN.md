---
style_id: notion
display_name: "따뜻한 정리형 (Notion 스타일)"
gui_summary: "따뜻한 미니멀리즘, 파스텔 카드, 편안한 워크스페이스 느낌. 커리어 타임라인/서술형 정리에 적합."
source: "VoltAgent/awesome-design-md (notion) 를 참고해 재구성. Notion 공식 자료가 아닌 비공식 분석 기반."
version: alpha
---

# 스타일 가이드: 따뜻한 정리형 (Notion 스타일)

## 무드
흰색 캔버스에 진한 네이비 히어로 밴드, 보라색 필(pill) 형태 버튼. 파스텔톤 카드(피치/로즈/민트/라벤더)로
정보를 색깔별로 분류해서 보여주는 느낌. 아이콘/일러스트가 곳곳에 들어가 친근한 인상을 줌.

## 색상
```yaml
colors:
  primary: "#5645d4"
  on-primary: "#ffffff"
  brand-navy: "#0a1530"
  card-tint-peach: "#ffe8d4"
  card-tint-rose: "#fde0ec"
  card-tint-mint: "#d9f3e1"
  card-tint-lavender: "#e6e0f5"
  card-tint-sky: "#dcecfa"
  canvas: "#ffffff"
  surface: "#f6f5f4"
  hairline: "#e5e3df"
  ink: "#1a1a1a"
  charcoal: "#37352f"
  slate: "#5d5b54"
  semantic-success: "#1aae39"
  semantic-error: "#e03131"
```

## 타이포그래피
```yaml
typography:
  heading-1:
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.15
  heading-3:
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.25
  body-md:
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
  caption:
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.40
```

## 형태 규칙
```yaml
rounded:
  sm: 6px
  md: 8px
  lg: 12px
  full: 9999px   # 버튼은 필(pill) 형태
spacing:
  xs: 8px
  sm: 12px
  md: 16px
  lg: 20px
  xl: 24px
```

## 이 스타일이 어울리는 프로필
경력/프로젝트를 스토리텔링처럼 서술하고 싶은 사람. 디자이너, 기획자처럼 텍스트와 카테고리 정리가
중요한 프로필. 여러 색깔로 태그(전공/동아리/관심분야)를 구분해서 보여주기 좋음.
