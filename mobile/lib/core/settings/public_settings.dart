import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

enum ThemeChoice { system, light, dark }

class SettingsFailure implements Exception {
  const SettingsFailure();

  @override
  String toString() => 'Connection settings could not be saved.';
}

class PublicSettings {
  const PublicSettings({this.origin, this.theme = ThemeChoice.system});
  final String? origin;
  final ThemeChoice theme;
  String encode() =>
      jsonEncode({'version': 1, 'origin': origin, 'theme': theme.name});
  factory PublicSettings.decode(String value) {
    if (value.length > 8192) throw const FormatException('Invalid settings');
    final data = jsonDecode(value);
    if (data is! Map<String, dynamic> ||
        data.length != 3 ||
        data['version'] != 1 ||
        data['version'] is! int ||
        !data.containsKey('origin') ||
        !data.containsKey('theme')) {
      throw const FormatException('Invalid settings');
    }
    final origin = data['origin'];
    if (origin != null && (origin is! String || origin.length > 2048)) {
      throw const FormatException('Invalid settings');
    }
    final themes = ThemeChoice.values.where(
      (theme) => theme.name == data['theme'],
    );
    if (themes.length != 1) throw const FormatException('Invalid settings');
    return PublicSettings(origin: origin as String?, theme: themes.single);
  }
}

abstract interface class SettingsStore {
  Future<PublicSettings> load();
  Future<void> save(PublicSettings value);
}

class MemorySettingsStore implements SettingsStore {
  PublicSettings _value = const PublicSettings();
  bool failWrites = false;
  @override
  Future<PublicSettings> load() async => _value;
  @override
  Future<void> save(PublicSettings value) async {
    if (failWrites) throw const SettingsFailure();
    _value = value;
  }
}

class PreferencesSettingsStore implements SettingsStore {
  PreferencesSettingsStore({SharedPreferencesAsync? preferences})
    : _preferences = preferences ?? SharedPreferencesAsync();
  final SharedPreferencesAsync _preferences;
  static const _key = 'bhli_public_settings';
  @override
  Future<PublicSettings> load() async {
    try {
      final value = await _preferences.getString(_key);
      return value == null
          ? const PublicSettings()
          : PublicSettings.decode(value);
    } catch (_) {
      throw const SettingsFailure();
    }
  }

  @override
  Future<void> save(PublicSettings value) async {
    try {
      await _preferences.setString(_key, value.encode());
    } catch (_) {
      throw const SettingsFailure();
    }
  }
}
