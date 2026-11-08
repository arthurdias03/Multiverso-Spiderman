# Segurança: trex-sync + spotifiBR

## O que proteger

| Ativo | Onde fica | Se vazar |
|---|---|---|
| Conta do Spotify (refresh token) | **Só no PC**, em `.spotify_token.json` (permissão 0600) | Leitura das suas playlists e curtidas. Não dá para alterar senha, e-mail, playlists ou plano: os escopos pedidos são só de leitura |
| Token do servidor de músicas | PC (`.trex_server_token`, 0600) e app Zepp no celular | Download das músicas que o seu PC está servindo. Não dá acesso à conta do Spotify nem a outros arquivos do PC |
| Arquivos do PC | PC | O servidor só entrega `manifest.json` e os MP3 listados nele |

Princípio do projeto: **o celular e o relógio nunca recebem credenciais do Spotify.**

## Defesas implementadas

**Conta do Spotify (PC)**
- Login OAuth com PKCE: não existe client secret para vazar.
- O `state` é verificado em tempo constante.
- Retorno do login aceito só em loopback (`127.0.0.1`).
- Escopos mínimos e só de leitura: `playlist-read-private`, `playlist-read-collaborative`, `user-library-read`.
- Arquivo de token gravado de forma atômica com permissão 0600. Arquivos antigos são corrigidos para 0600.

**Servidor (`python -m trex_sync servir`)**
- Token obrigatório de 256 bits, gerado automaticamente. O servidor recusa tokens com menos de 32 caracteres.
- O token vai **só no cabeçalho** `X-Trex-Token`. Token na URL é recusado, porque URLs acabam em logs e histórico.
- Comparação em tempo constante e bloqueio de 15 min por IP após 10 tentativas erradas.
- Allowlist: só `manifest.json` e os arquivos listados nele. Não há listagem de pastas. Arquivos internos (`.trex_state.json`, `_FALTANDO.txt`, `_PARA_TRANSFERIR/`) nunca saem.
- Caminho real conferido: um symlink que aponte para fora da pasta é bloqueado. `..`, `%2e%2e` e bytes nulos são rejeitados.
- Por padrão escuta só na interface da rede local (`server_bind: "auto"`) e recusa clientes com IP público.
- Só aceita GET e HEAD. Timeout de 30 s por conexão. Cabeçalhos `nosniff` e `no-store`.
- Logs sem query string e sem segredos.
- TLS opcional (`tls_cert`/`tls_key`, TLS 1.2 ou superior).

**Processamento (PC)**
- Nomes de playlist e de música vêm de terceiros (playlists públicas e colaborativas). Eles são higienizados: sem `/`, sem `..`, sem ponto inicial, sem nomes reservados do Windows. Há também uma checagem final de que o caminho fica dentro de `saida/`.
- Downloader externo opcional: roda sem shell, aceita só URL de faixa do Spotify, remove `-` inicial dos metadados (evita injeção de opções como `--exec=...`) e tem timeout.
- IDs do Spotify validados (`[A-Za-z0-9]{1,64}`) antes de virarem URL ou nome de arquivo.

**App Zepp (celular e relógio)**
- Endereço do servidor validado: `https` para qualquer host; `http` só para IPs de rede privada, assim o token nunca atravessa a internet em texto puro. Endereços com usuário/senha ou query são recusados.
- O manifesto é validado e limitado (IDs, caminhos, tamanhos, quantidades, textos), duas vezes: no celular e de novo no relógio.
- Arquivo recebido só é aceito se o ID está no manifesto e o tamanho confere. Caso contrário, é apagado.
- Permissões mínimas no relógio: só `device:os.bg_service`, necessária para tocar em segundo plano.
- Dependência `@zeppos/zml` (oficial da Zepp) fixada em versão exata, com `package-lock.json`.
- Botão "Apagar endereço e token deste celular" nas configurações.

## Riscos que continuam (decisão sua)

| Risco | Mitigação |
|---|---|
| Em `http`, quem está no mesmo Wi-Fi e captura tráfego vê o token e as músicas (não a conta) | Use só no Wi-Fi de casa, ou HTTPS via Tailscale (abaixo) |
| O token fica salvo sem cifra no armazenamento do app Zepp no celular | O Zepp OS não oferece cofre. O alcance do token é limitado; se perder o celular, rode `novo-token` |
| O campo de token nas configurações do Zepp não é mascarado | Limitação do componente do Zepp |
| App instalado em modo desenvolvedor, sem revisão da loja | O código-fonte está todo aqui; revise antes de instalar |
| Não houve teste de invasão em aparelho real | Os testes automatizados cobrem os ataques listados acima |

## Recomendado: acesso cifrado com Tailscale (grátis para uso pessoal)

Tailscale cria uma rede privada cifrada entre os seus aparelhos. Com ele você tem HTTPS com certificado válido e acesso fora de casa, sem abrir portas no roteador:

1. Instale o Tailscale no PC e no iPhone, com a mesma conta.
2. No `config.json`, defina `"server_bind": "127.0.0.1"`.
3. No PC: `python -m trex_sync servir` e, em outro terminal, `tailscale serve --bg 8765`.
4. No app Zepp, use o endereço `https://<nome-do-pc>.<sua-tailnet>.ts.net`.

Use `tailscale serve`, que deixa o acesso só na sua rede privada. **Nunca use `tailscale funnel`**: ele publica o servidor na internet.

## Se algo vazar

- **Celular perdido ou token exposto:** `python -m trex_sync novo-token` invalida o token antigo na hora.
- **Arquivo `.spotify_token.json` exposto:** em spotify.com/account/apps, remova o acesso do app e apague o arquivo. Depois rode `login` de novo.
