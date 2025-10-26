import {DarkTheme, DefaultTheme, ThemeProvider} from '@react-navigation/native';
import {StatusBar} from 'expo-status-bar';
import {Text} from 'react-native';
import 'react-native-reanimated';

import {useColorScheme} from '@/hooks/use-color-scheme';
import HealthKit, {
  AuthorizationRequestStatus,
  UpdateFrequency,
  useHealthkitAuthorization
} from "@kingstinct/react-native-healthkit";
import {useEffect} from "react";
import HomeScreen from "@/app/index";
import {QueryClient, QueryClientProvider} from "@tanstack/react-query";

const queryClient = new QueryClient()

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [authStatus, requestAuthorization] = useHealthkitAuthorization(["HKQuantityTypeIdentifierHeartRate"]);

  useEffect(() => {
    requestAuthorization();

    HealthKit.enableBackgroundDelivery(
      "HKCategoryTypeIdentifierHighHeartRateEvent",
      UpdateFrequency.immediate,
    )

    HealthKit.enableBackgroundDelivery(
      "HKQuantityTypeIdentifierHeartRate",
      UpdateFrequency.immediate,
    )
  }, [authStatus, requestAuthorization]);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
          {authStatus !== AuthorizationRequestStatus.unnecessary ? (
            <Text>Please allow Koors to read your heart rate</Text>
          ) : (
            <HomeScreen />
          )}
        <StatusBar style="auto" />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
