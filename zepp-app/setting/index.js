import { checkServerUrl, checkToken } from '../lib/validate'

AppSettingsPage({
  build(props) {
    const store = props.settingsStorage
    const get = (k) => store.getItem(k) || ''
    const set = (k) => (v) => store.setItem(k, String(v || '').trim())

    const url = checkServerUrl(get('serverUrl'))
    const tok = checkToken(get('token'))
    const status = !get('serverUrl')
      ? 'Não configurado'
      : !url.ok
        ? url.error
        : !tok.ok
          ? tok.error
          : url.secure
            ? 'OK (conexão cifrada)'
            : 'OK (rede local, sem cifra: use só no Wi-Fi de casa)'

    return Section({}, [
      View({ style: { padding: '16px' } }, [
        Text({ bold: true, paragraph: true }, ['spotifiBR']),
        Text({ paragraph: true, style: { color: '#666', fontSize: '14px' } }, [
          'Rode "python -m trex_sync servir" no computador e copie o endereço e o token mostrados.',
        ]),
        Text({ paragraph: true, style: { fontSize: '14px', color: url.ok && tok.ok ? '#1a7f37' : '#b42318' } }, [
          `Status: ${status}`,
        ]),
      ]),
      TextInput({
        label: 'Endereço do servidor',
        placeholder: 'http://192.168.0.10:8765',
        value: get('serverUrl'),
        onChange: set('serverUrl'),
      }),
      TextInput({
        label: 'Token',
        placeholder: 'token mostrado pelo trex-sync',
        value: get('token'),
        onChange: set('token'),
      }),
      View({ style: { padding: '16px' } }, [
        Text({ paragraph: true, style: { color: '#666', fontSize: '13px' } }, [
          'O token dá acesso só às músicas servidas pelo seu PC, nunca à sua conta do Spotify. ',
          'Se o celular for perdido, rode "python -m trex_sync novo-token" no PC.',
        ]),
        Button({
          label: 'Apagar endereço e token deste celular',
          color: 'secondary',
          onClick: () => {
            store.removeItem('serverUrl')
            store.removeItem('token')
          },
        }),
      ]),
    ])
  },
})
