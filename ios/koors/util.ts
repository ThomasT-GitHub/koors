import Peripheral, { Service, Characteristic } from 'react-native-peripheral'

Peripheral.onStateChanged(state => {
  if (state === 'poweredOn') {
    Peripheral.startAdvertising({
      name: 'My BLE device',
      serviceUuids: ['test-uuid'],
    })
  }
})
