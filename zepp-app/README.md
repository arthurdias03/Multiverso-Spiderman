# T-Rex Music: app do relógio (Zepp OS)

Mini-app para o **Amazfit T-Rex 3** (Zepp OS 4.x, API_LEVEL 4.0, tela redonda 480×480). Ele:

1. **Sincroniza ao abrir:** pede ao celular (app Zepp) o `manifest.json` do servidor `trex-sync`, compara com o que já está no relógio, baixa **só as faixas novas**, apaga as que saíram das playlists e recupera arquivos que chegaram com o app fechado.
2. **Toca offline**, por playlist, em ordem ou aleatório. A reprodução roda num *App Service* e continua com a tela apagada e depois que você sai do app.

```
PC: python -m trex_sync servir ──HTTP (Wi-Fi)──> Celular: app Zepp (side service)
                                                    │  baixa o MP3
                                                    ▼  TransferFile (Bluetooth)
                                                 Relógio: T-Rex Music → /data/music/<id>.mp3
```

## Estrutura

| Pasta | Onde roda | Função |
|---|---|---|
| `page/home.js` | relógio | sincronização + lista de playlists |
| `page/playlist.js` | relógio | faixas, Tocar / Aleatório |
| `page/player.js` | relógio | tocando agora, anterior/pausar/próxima (botões físicos cima/baixo) |
| `app-service/player_service.js` | relógio (segundo plano) | player `@zos/media` |
| `lib/storage.js` | relógio | biblioteca local, diferenças e arquivos |
| `app-side/index.js` | celular (app Zepp) | busca o manifesto, baixa e transfere a fila |
| `setting/index.js` | celular (app Zepp) | tela de configuração: endereço e token do servidor |

## Instalar no relógio

1. Instale o Node 18+ e o compilador: `npm i -g @zeppos/zeus-cli`.
2. Crie uma conta de desenvolvedor em https://console.zepp.com, crie um Mini Program e **troque o `appId` em `app.json`** pelo seu (o `1098765` atual é um valor provisório).
3. No celular, ative o modo desenvolvedor do app Zepp: Perfil → Configurações → Sobre → toque 7× no logo.
4. Gere o pacote:
   ```bash
   cd zepp-app
   npm install
   zeus login
   zeus preview      # escolha o T-Rex 3; aparece um QR code
   ```
5. No app Zepp: Perfil → Developer Mode → Scan, e leia o QR. O app é instalado no relógio.
6. No app Zepp: Perfil → T-Rex 3 → Apps → T-Rex Music → Configurações. Preencha o **endereço** e o **token** que o `python -m trex_sync servir` mostra.

## Uso diário

1. No PC, depois de adicionar músicas no Spotify: `python -m trex_sync servir --sync`.
2. No relógio, abra o **T-Rex Music**. Ele baixa as novas sozinho. Deixe o app aberto até aparecer "Sincronização concluída" (a tela fica acesa durante a transferência).
3. Escolha uma playlist e toque **Tocar** ou **Aleatório**. Conecte os fones Bluetooth antes, pelo menu do próprio relógio.

## Testes

```bash
npm test        # lógica da biblioteca (diferença, remoção, recuperação) com @zos/fs simulado
zeus build      # compila o pacote .zab
```

## Limitações (com nível de confiança)

| Limitação | Motivo | Confiança |
|---|---|---|
| Transferência lenta (estimativa: minutos por música) | Bluetooth LE. Use `mp3_bitrate` 96k–128k no `config.json` | média |
| Só sincroniza com o app **aberto** no relógio | O side service vive enquanto o app do relógio está ativo; não existe gatilho de "relógio conectou" para mini-apps | alta |
| Pausar e retomar recomeça a faixa | O T-Rex 3 está no API_LEVEL 4.0; `seek` só existe a partir do 4.2 | alta |
| "Tocando agora" pode mostrar a faixa anterior se ela trocou com a tela ligada | O App Service só pode gravar arquivos com a tela apagada | alta |
| As músicas não aparecem no player de música nativo do relógio | Mini-apps não têm acesso à biblioteca de música do sistema | alta |
| Saída nos fones Bluetooth | O player usa a saída de áudio do sistema; não deu para testar num aparelho real | média |
| PC e celular precisam estar na mesma rede | O servidor é local. Para uso fora de casa, publique a pasta `saida/` via HTTPS (ex.: Tailscale/Cloudflare Tunnel) | alta |

**Não testado em aparelho real.** O código segue a documentação oficial do Zepp OS e compila com o `zeus build`, mas não rodou num T-Rex 3 nem no simulador. Os pontos mais prováveis de precisar de ajuste são: o caminho onde o arquivo recebido é gravado (`file.filePath`), o comportamento do `appService.start/stop` e o layout.
