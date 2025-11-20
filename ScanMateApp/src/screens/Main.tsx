// src/screens/Main.tsx
import React from 'react';
import {View, Text, Button, StyleSheet} from 'react-native';
// src/screens/Main.tsx
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../../App'; // Import the "map"

// This component receives a 'navigation' prop from the navigator
// Define the prop types for this screen
type Props = NativeStackScreenProps<RootStackParamList, 'Main'>;

export const Main = ({navigation}: Props) => { 

  const onScanPress = () => {
    // This tells the navigator to go to the "ScanBoard" screen
    navigation.navigate('ScanBoard');
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>ScanMate</Text>
      <Button title="Scan Chessboard" onPress={onScanPress} />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F5FCFF',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
  },
});