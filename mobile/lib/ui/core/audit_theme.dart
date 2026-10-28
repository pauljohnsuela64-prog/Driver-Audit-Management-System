import 'package:flutter/material.dart';

ThemeData auditTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme =
      ColorScheme.fromSeed(
        seedColor: const Color(0xff0f766e),
        brightness: brightness,
      ).copyWith(
        primary: Color(dark ? 0xff2dd4bf : 0xff0f766e),
        onPrimary: Color(dark ? 0xff0b1220 : 0xffffffff),
        surface: Color(dark ? 0xff111c2e : 0xffffffff),
        onSurface: Color(dark ? 0xfff1f5f9 : 0xff0f172a),
        onSurfaceVariant: Color(dark ? 0xffb8c5d6 : 0xff475569),
        outline: Color(dark ? 0xff71839b : 0xff64748b),
        error: Color(dark ? 0xfffca5a5 : 0xffb91c1c),
      );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: Color(dark ? 0xff0b1220 : 0xfff1f5f9),
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      centerTitle: false,
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(),
      alignLabelWithHint: true,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        padding: const EdgeInsets.all(16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        padding: const EdgeInsets.all(16),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
  );
}
