AppSettingsPage({
  build(props) {
    const get = (k) => props.settingsStorage.getItem(k) || ''
    const set = (k) => (v) => props.settingsStorage.setItem(k, String(v || '').trim())

    return Section({}, [
      View({ style: { padding: '16px' } }, [
        Text({ bold: true, paragraph: true }, ['T-Rex Music']),
        Text({ paragraph: true, style: { color: '#666', fontSize: '14px' } }, [
          'Rode "python -m trex_sync servir" no computador (mesmo Wi-Fi do celular) e copie o endereço e o token mostrados.',
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
        placeholder: 'o mesmo de server_token no config.json',
        value: get('token'),
        onChange: set('token'),
      }),
      View({ style: { padding: '16px' } }, [
        Text({ paragraph: true, style: { color: '#666', fontSize: '13px' } }, [
          'Depois, abra o T-Rex Music no relógio: ele baixa sozinho as músicas novas de cada playlist. ',
          'Mantenha o app aberto no relógio durante a transferência.',
        ]),
      ]),
    ])
  },
})
