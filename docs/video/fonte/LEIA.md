# Fonte do vídeo

`video.html` contém as cenas (animadas por `setTime(t)`), e `render.js` grava quadro a quadro com o Playwright e gera o MP4 com o ffmpeg:

```bash
node render.js            # gera spotifibr.mp4 (1920x1080, 30 fps)
```
