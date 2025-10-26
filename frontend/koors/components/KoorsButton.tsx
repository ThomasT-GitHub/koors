import {Animated, Pressable, StyleSheet, Text} from "react-native";
import {ReactNode, useMemo, useRef} from "react";

interface KoorsButtonProps {
  onPress?: () => void,
  onPressIn?: () => void,
  onPressOut?: () => void,
  variant?: 'accent' | 'transparent',
  children: ReactNode | ReactNode[]
}

const accentRange = ['#3c83ff', '#5993ff']
const transparentRange = ['#ffffff00', '#f6f6f6ff']

export default function KoorsButton({ children, variant = 'accent', onPress = () => {}, onPressOut = () => {}, onPressIn = () => {} }: KoorsButtonProps) {
  const animatedColor = useRef(new Animated.Value(0)).current;
  const animatedScale = useRef(new Animated.Value(0)).current;

  const colorRange = useMemo(() => {
    switch (variant) {
      case 'accent':
        return accentRange
      case 'transparent':
        return transparentRange
    }
  }, [variant])

  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => {
        Animated.timing(animatedColor, {
          toValue: 1,
          duration: 80,
          useNativeDriver: true,
        }).start();
        Animated.spring(animatedScale, {
          toValue: 1,
          friction: 5,
          velocity: 25,
          useNativeDriver: true,
        }).start();
        onPressIn()
      }}
      onPressOut={() => {
        Animated.timing(animatedColor, {
          toValue: 0,
          duration: 80,
          useNativeDriver: true,
        }).start();
        Animated.spring(animatedScale, {
          toValue: 0,
          friction: 5,
          velocity: -25,
          useNativeDriver: true,
        }).start();
        onPressOut()
      }}
    >
      <Animated.View
        style={[
          styles.button,
          {
            backgroundColor: animatedColor.interpolate({
              inputRange: [0, 1],
              outputRange: colorRange,
            }),
            transform: [{scale: animatedScale.interpolate({
              inputRange: [0, 1],
              outputRange: [1, 0.95],
            })}]
          },
        ]}
      >
        <Text style={[styles.buttonText, variant === 'transparent' ? styles.textTransparent : {}]}>
          {children}
        </Text>
      </Animated.View>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  button: {
    paddingLeft: 20,
    paddingRight: 20,
    paddingTop: 15,
    paddingBottom: 15,
    borderRadius: 15,
    width: '100%',
    alignItems: 'center',
  },

  buttonText: {
    color: 'white',
    fontSize: 20,
    fontWeight: 'bold',
  },

  textTransparent: {
    color: 'black'
  },
})
