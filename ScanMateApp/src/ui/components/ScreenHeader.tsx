import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet, StyleProp, ViewStyle, TextStyle} from 'react-native';

interface ScreenHeaderProps {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  showBackButton?: boolean;
  style?: StyleProp<ViewStyle>;
  titleStyle?: StyleProp<TextStyle>;
  subtitleStyle?: StyleProp<TextStyle>;
}

export const ScreenHeader: React.FC<ScreenHeaderProps> = ({
  title,
  subtitle,
  onBack,
  showBackButton = true,
  style,
  titleStyle,
  subtitleStyle,
}) => {
  const subtitleText = subtitle ?? ' ';
  return (
    <View style={[styles.container, style]}>
      <View style={styles.row}>
        {showBackButton ? (
          <TouchableOpacity
            onPress={onBack}
            style={styles.backButton}
            hitSlop={{top: 12, bottom: 12, left: 12, right: 12}}
          >
            <Text style={styles.backText}>←</Text>
          </TouchableOpacity>
        ) : (
          <View style={styles.backPlaceholder} />
        )}
        <View pointerEvents="none" style={styles.titleWrapper}>
          <Text style={[styles.title, titleStyle]} numberOfLines={1}>
            {title}
          </Text>
        </View>
        <View style={styles.trailingSpacer} />
      </View>
      <Text style={[styles.subtitle, subtitleStyle]} numberOfLines={1}>
        {subtitleText}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  backText: {
    fontSize: 18,
    color: '#ffffff',
    fontWeight: '700',
  },
  backPlaceholder: {
    width: 40,
    height: 40,
  },
  titleWrapper: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: '#ffffff',
    textAlign: 'center',
  },
  trailingSpacer: {
    width: 40,
    height: 40,
  },
  subtitle: {
    marginTop: 6,
    color: '#aaaaaa',
    fontSize: 14,
    minHeight: 18,
    textAlign: 'center',
  },
});
