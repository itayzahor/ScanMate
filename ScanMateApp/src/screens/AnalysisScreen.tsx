import React from 'react';
import {View, Text, StyleSheet, TouchableOpacity} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../../App';

type AnalysisProps = NativeStackScreenProps<RootStackParamList, 'Analysis'>;

export const AnalysisScreen = ({route, navigation}: AnalysisProps) => {
  const {fen} = route.params;

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Board Analysis</Text>
      <Text style={styles.label}>FEN Output</Text>
      <View style={styles.fenBox}>
        <Text style={styles.fenText}>{fen}</Text>
      </View>

      <TouchableOpacity style={styles.button} onPress={() => navigation.popToTop()}>
        <Text style={styles.buttonText}>Back to Home</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0B0B0D',
    padding: 24,
    justifyContent: 'center',
  },
  title: {
    fontSize: 24,
    color: '#FFFFFF',
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 24,
  },
  label: {
    fontSize: 16,
    color: '#B0B0B5',
    marginBottom: 12,
  },
  fenBox: {
    backgroundColor: '#1C1C1E',
    borderRadius: 12,
    padding: 16,
    minHeight: 120,
    justifyContent: 'center',
    marginBottom: 24,
  },
  fenText: {
    color: '#EDEDED',
    fontSize: 18,
    textAlign: 'center',
  },
  button: {
    backgroundColor: '#FF3B30',
    borderRadius: 25,
    paddingVertical: 14,
    alignItems: 'center',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});
