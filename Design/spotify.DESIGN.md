---
style_id: spotify
display_name: "다크 임팩트 (Spotify 스타일)"
gui_summary: "어두운 배경에 비비드 그린 포인트, 필/원형 버튼. 프로젝트를 앨범 커버처럼 강조하고 싶은 프로필에 적합."
source: "VoltAgent/awesome-design-md (spotify) 를 참고해 재구성. Spotify 공식 자료가 아닌 비공식 분석 기반."
version: alpha
---

# 스타일 가이드: 다크 임팩트 (Spotify 스타일)

## 무드
근접 블랙(#121212~#1f1f1f) 배경 위에 콘텐츠(프로젝트 썸네일 등)가 돋보이게 하는 "콘텐츠 우선 암전" 컨셉.
브랜드 컬러는 오직 스포티파이 그린(#1ed760) 하나만 기능적으로 사용. 버튼은 완전한 필/원형.

## 색상
```yaml
colors:
  primary: "#1ed760"
  canvas: "#121212"
  surface-1: "#181818"
  surface-2: "#1f1f1f"
  card: "#252525"
  text-base: "#ffffff"
  text-muted: "#b3b3b3"
  border: "#4d4d4d"
  semantic-error: "#f3727f"
  semantic-warning: "#ffa42b"
  semantic-info: "#539df5"
```

## 타이포그래피
```yaml
typography:
  heading:
    fontWeight: 700
    letterSpacing: -0.2px
  subheading:
    fontWeight: 600
  body:
    fontWeight: 400
  button:
    fontWeight: 700
    textTransform: uppercase
    letterSpacing: 1.6px
```

## 형태 규칙
```yaml
rounded:
  button: 9999px   # 완전한 필 형태
  play-control: 50%  # 원형
shadow:
  elevated: "rgba(0,0,0,0.5) 0px 8px 24px"
  card: "rgba(0,0,0,0.3) 0px 8px 8px"
```

## 이 스타일이 어울리는 프로필
프로젝트/포트폴리오 이미지(스크린샷, 앱 아이콘 등)를 크게 보여주고 싶은 사람. 게임 개발,
미디어, 크리에이티브 계열처럼 시각적 임팩트가 중요한 프로필.
