// App.tsx

import React, {useEffect, useState} from 'react';
import {ActivityIndicator, Text, View, StyleSheet} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {useCameraPermission} from 'react-native-vision-camera';

// Import from your new file structure
import {Main} from './src/screens/Main';
import {ScanBoard} from './src/screens/ScanBoard';
import {ResultScreen} from './src/screens/ResultScreen';
import {AnalysisScreen} from './src/screens/AnalysisScreen';

// This defines all your screens and what parameters they take
export type RootStackParamList = {
  Main: undefined; // Main screen takes no parameters
  ScanBoard: undefined; // ScanBoard screen takes no parameters
  Result: { photoPath: string }; // Result screen takes a photoPath parameter
  Analysis: { fen: string }; // Analysis screen shows the resulting FEN
};

// This tells the navigator to use that "map"
const Stack = createNativeStackNavigator<RootStackParamList>();

const App = () => {
  const {hasPermission, requestPermission} = useCameraPermission();
  const [isReady, setIsReady] = useState(false);

  // Check for camera permission *before* loading the app
  useEffect(() => {
    const getPermission = async () => {
      if (hasPermission) {
        setIsReady(true);
        return;
      }
      const granted = await requestPermission();
      if (!granted) {
        console.log('Permission denied');
      }
      setIsReady(true); // Ready to load, even if permission denied
    };
    getPermission();
  }, [hasPermission, requestPermission]);

  // Show a loading spinner while checking permission
  if (!isReady) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  // If permission is denied, show a message and don't load the app
  if (!hasPermission) {
    return (
      <View style={styles.container}>
        <Text style={styles.text}>
          Camera permission is required to use ScanMate.
        </Text>
        <Text style={styles.text}>Please restart the app and grant permission.</Text>
      </View>
    );
  }

  // Permission is granted, load the full app navigator
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen
          name="Main"
          component={Main} // Use your Main component
          options={{title: 'ScanMate Home'}}
        />
        <Stack.Screen
          name="ScanBoard" // Use your new screen name
          component={ScanBoard} // Use your ScanBoard component
          options={{
            headerShown: false,
            freezeOnBlur: false, // ⬅️ ADD THIS LINE
          }}
        />
        <Stack.Screen
          name="Result" // ⬅️ NEW SCREEN REGISTERED HERE
          component={ResultScreen}
          options={{title: 'Confirm Photo'}}
        />
        <Stack.Screen
          name="Analysis"
          component={AnalysisScreen}
          options={{title: 'Analysis'}}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  text: {
    fontSize: 18,
    textAlign: 'center',
    padding: 20,
  },
});

export default App;