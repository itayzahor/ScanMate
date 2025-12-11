/**
 * @format
 */
import {LogBox} from 'react-native';
import Reanimated from 'react-native-reanimated';

const reanimatedValueWarning =
  "[Reanimated] Reading from `value` during component render";

const originalWarn = console.warn;
console.warn = (message, ...args) => {
  if (typeof message === 'string' && message.includes(reanimatedValueWarning)) {
    return;
  }
  originalWarn(message, ...args);
};

if (typeof Reanimated?.setLogger === 'function') {
  Reanimated.setLogger({
    log: console.log,
    error: console.error,
    warn: (message, ...args) => {
      if (
        typeof message === 'string' &&
        message.includes(reanimatedValueWarning)
      ) {
        return;
      }
      console.warn(message, ...args);
    },
  });
}

// Ignore the yellow-box entry too so dev menu stays quiet
LogBox.ignoreLogs([reanimatedValueWarning]);

import 'react-native-gesture-handler';
import { AppRegistry } from 'react-native';
import App from './App';
import { name as appName } from './app.json';

AppRegistry.registerComponent(appName, () => App);
