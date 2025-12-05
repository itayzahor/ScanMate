import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { ScanBoard } from "../screens/ScanBoard";
import { ResultScreen } from "../screens/ResultScreen";
import AnalysisScreen from "../screens/Analysis";
import type { RootStackParamList } from "../../App";

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const stackScreens = (
    <>
      <Stack.Screen
        name="ScanBoard"
        component={ScanBoard}
        options={{ title: "Scan Chessboard" }}
      />
      <Stack.Screen
        name="Result"
        component={ResultScreen}
        options={{ title: "Board Result" }}
      />
      <Stack.Screen
        name="Analysis"
        component={AnalysisScreen}
        options={{ title: "Analysis" }}
      />
    </>
  );

  return (
    <NavigationContainer
      children={
        <Stack.Navigator
          initialRouteName="ScanBoard"
          children={stackScreens}
        />
      }
    />
  );
}
