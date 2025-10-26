import {Animated, Text, StyleSheet, View} from 'react-native';
import {useEffect, useMemo, useRef, useState} from "react";
import HealthKit, {
  useMostRecentQuantitySample,
} from "@kingstinct/react-native-healthkit";
import KoorsButton from "@/components/KoorsButton";
import {startAdvertising, stopAdvertising} from "munim-bluetooth-peripheral";
import Voice from '@react-native-voice/voice';
import {useMutation, useQuery} from "@tanstack/react-query";

const koorsIp = "172.20.10.7"

export default function HomeScreen() {
  const [heartRate, setHeartRate] = useState(useMostRecentQuantitySample("HKQuantityTypeIdentifierHeartRate")?.quantity ?? 0);
  const [isListening, setIsListening] = useState(false);
  const [showVoiceUI, setShowVoiceUI] = useState(false);
  const [liveVoiceTranscription, setLiveVoiceTranscription] = useState<string>("");
  const [commandRecognized, setCommandRecognized] = useState<boolean | null>(null)
  const transcriptionRef = useRef("");

  const backdropRef = useRef(new Animated.Value(0)).current
  const commandColorRef = useRef(new Animated.Value(0)).current
  const commandAnimRef = useRef(new Animated.Value(1)).current

  // Communication with Koors
  const koorsStatusQuery = useQuery({
    queryKey: ['koorsStatus'],
    queryFn: async () => {
      console.log("attempting to get status...")
      const resp = await fetch(`http://${koorsIp}:8080/dispatch_status`)
      const jsonResp = await resp.json()
      return jsonResp["status"]
    },
    refetchInterval: 1000,
  })
  console.log(koorsStatusQuery.data)

  const performMutation = useMutation({
    mutationFn: async (command: string) => {
      console.log("attempting to perform command " + command)
      const resp = await fetch(`http://${koorsIp}:8080/perform?action=${command}`, {
        method: "POST",
      })
    }
  })

  const dispatchMutation = useMutation({
    mutationFn: async () => {
      console.log("attempting to dispatch")
      const resp = await fetch(`http://${koorsIp}:8080/dispatch`, {
        method: "POST",
      })
    }
  })

  // Listen live while the app is open
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const sample = await HealthKit.getMostRecentQuantitySample("HKQuantityTypeIdentifierHeartRate")
        if (sample) {
          setHeartRate(sample.quantity)
        }
      } catch (e) {
        console.error("Error getting most recent sample:", e)
      }
    }, 1000 * 5);

    return () => {
      clearInterval(id)
    }
  }, []);

  const beatingHeartAnim = useRef(new Animated.Value(1.1)).current
  useEffect(() => {
    const anim = Animated.loop(
      Animated.timing(beatingHeartAnim, {
        toValue: 1,
        duration: Math.round((60 / (heartRate + 1)) * 1000),
        useNativeDriver: true,
      }),
      {
        iterations: -1,
      },
    )

    anim.start()

    return () => {
      anim.stop()
    }
  }, [heartRate]);

  const koorsState: 'searching' | 'ready' | 'unknown' = useMemo(() => {
    if (koorsStatusQuery.data === "dispatched") {
      return 'searching'
    } else if (koorsStatusQuery.data === "ready") {
      return 'ready'
    } else {
      return 'unknown'
    }
  }, [koorsStatusQuery.data])

  const [koorsStateText, koorsStateColor] = useMemo(() => {
    switch (koorsState) {
      case 'ready':
        return ['Ready', '#2da400']
      case 'searching':
        return ['Searching...', '#d5af00']
      case 'unknown':
        return ['Unknown', '#575757']
    }
  }, [koorsState])

  useEffect(() => {
    Voice.onSpeechResults = (event) => {
      console.log('Speech results:', event.value);
      if (event.value && event.value.length > 0) {
        const command = event.value[0].toLowerCase();
        console.log("COMMAND: " + command);
        setLiveVoiceTranscription(command)
        transcriptionRef.current = command
      }
    };

    Voice.onSpeechEnd = () => {
      console.log('Speech ended');
    };

    Voice.onSpeechError = (error) => {
      console.error('Speech error:', error);
      setIsListening(false);
    };

    return () => {
      Voice.destroy().then(Voice.removeAllListeners);
    };
  }, []);

  const startListening = async () => {
    try {
      await Voice.start('en-US');
      setIsListening(true);
      setShowVoiceUI(true);
      setCommandRecognized(null)
      commandColorRef.setValue(0)
      commandAnimRef.setValue(1)
      setLiveVoiceTranscription("")

      Animated.timing(backdropRef, {
        toValue: 1,
        duration: 80,
        useNativeDriver: true,
      }).start()
    } catch (error) {
      console.error('Error starting voice recognition:', error);
    }
  };

  const stopListening = async () => {
    try {
      setTimeout(async () => {
        await Voice.stop();
      }, 500)
    } catch (error) {
      console.error('Error stopping voice recognition:', error);
    }

    setIsListening(false);
    setTimeout(() => processCommand(), 750)
  };

  useEffect(() => {
    startAdvertising({
      serviceUUIDs: ['180D', '180F'],
      localName: 'Koors Beacon',
      manufacturerData: '0102030405',
    });

    return () => {
      stopAdvertising()
    }
  }, [])

  const fadeOutVoiceUI = () => {
    Animated.timing(backdropRef, {
      toValue: 0,
      duration: 80,
      useNativeDriver: true,
    }).start(() => {
      setShowVoiceUI(false)
    })
  }

  const processCommand = () => {
    console.log("FINAL COMMAND => " + transcriptionRef.current)

    // Match up command
    const command = transcriptionRef.current.toLowerCase()
    let realizedCommand = null
    if (command.includes("flip")) {
      realizedCommand = "flip"
    } else if (command.includes("help")) {
      realizedCommand = "help"
    }

    if (realizedCommand) {
      setCommandRecognized(true)
    } else {
      setCommandRecognized(false)
    }

    Animated.timing(commandColorRef, {
      toValue: 1,
      duration: 80,
      useNativeDriver: false,
    }).start(() => {
      setTimeout(fadeOutVoiceUI, 500)
    })

    commandAnimRef.setValue(1.1)
    Animated.timing(commandAnimRef, {
      toValue: 1,
      duration: 80,
      useNativeDriver: false,
    }).start()

    // Send mutation
    if (realizedCommand) {
        performMutation.mutate(realizedCommand)
    }
  }

  const commandColor = useMemo(() => {
    if (commandRecognized === true) {
      return '#2da400'
    } else if (commandRecognized === false) {
      return '#d50000'
    } else {
      return '#ffffff'
    }
  }, [commandRecognized])

  return (
      <View style={styles.centerContainer}>
        <View style={styles.container}>
          <View style={styles.titleContainer}>
            <Text style={styles.title}>🐕 koors.</Text>
          </View>

          <View style={styles.infoContainer}>
            <Text style={styles.subLabel}>Last Heartrate</Text>
            <View style={styles.heartRateTextContainer}>
              <Animated.Text style={[styles.beatingHeart, {transform: [{scale: beatingHeartAnim}]}]}>❤️</Animated.Text>
              <Text style={styles.valueText}>{Math.round(heartRate)} BPM</Text>
            </View>
          </View>

          <View style={styles.infoContainer}>
            <Text style={styles.subLabel}>Koors is...</Text>
            <Text style={[styles.valueText, {color: koorsStateColor}]}>{koorsStateText}</Text>
          </View>

          <View style={styles.buttons}>
            <KoorsButton
              onPress={() => dispatchMutation.mutate()}
            >
              Koors, IM DYING!
            </KoorsButton>
            <KoorsButton
              variant="transparent"
              onPressIn={startListening}
              onPressOut={stopListening}
            >
              Koors, LISTEN!
            </KoorsButton>
          </View>
        </View>

        {showVoiceUI && (
          <Animated.View style={[styles.backdrop, { opacity: backdropRef }]}>
            <Animated.Text
              style={[
                styles.transcriptionText,
                {
                  color: commandColorRef.interpolate({
                    inputRange: [0, 1],
                    outputRange: ['#ffffff', commandColor]
                  }),
                  transform: [{scale: commandAnimRef}]
                }
              ]}
            >
              {liveVoiceTranscription}
            </Animated.Text>
          </Animated.View>
        )}
      </View>
  );
}

const styles = StyleSheet.create({
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },

  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'stretch',
    gap: 30,
    width: 275,
  },

  titleContainer: {
    transformOrigin: [0, 0, 0],
    transform: [{scaleX: 1.25}]
  },

  title: {
    fontSize: 64,
    fontWeight: 'bold'
  },

  infoContainer: {
    alignItems: 'flex-start',
  },

  subLabel: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#555'
  },

  heartRateTextContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },

  valueText: {
    fontWeight: 'bold',
    fontSize: 42,
  },

  beatingHeart: {
    fontSize: 42,
    transform: [{scale: 2}]
  },

  buttons: {
    gap: 10
  },

  backdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
    padding: 50,
  },

  transcriptionText: {
    fontSize: 32,
    fontWeight: 'bold',
    color: 'white',
    textAlign: 'center',
  }
});
