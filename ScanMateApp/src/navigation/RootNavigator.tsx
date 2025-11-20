import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import ScanBoardScreen from "../screens/ScanBoard";
import ResultScreen from "../screens/Analysis";

export type RootStackParamList = {
  ScanBoard: undefined;
  Result: { fen: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="ScanBoard">
        <Stack.Screen
          name="ScanBoard"
          component={ScanBoardScreen}
          options={{ title: "Scan Chessboard" }}
        />
        <Stack.Screen
          name="Result"
          component={ResultScreen}
          options={{ title: "Board Result" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
