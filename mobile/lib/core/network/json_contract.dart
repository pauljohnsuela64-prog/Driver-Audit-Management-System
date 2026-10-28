import 'api_failure.dart';

Map<String, dynamic> jsonObject(Object? value) {
  if (value is! Map<String, dynamic>) throw ApiFailure.protocol;
  return value;
}

int positiveInt(Object? value) {
  if (value is! int || value < 1) throw ApiFailure.protocol;
  return value;
}

int? nullablePositiveInt(Map<String, dynamic> json, String key) {
  if (!json.containsKey(key)) throw ApiFailure.protocol;
  return json[key] == null ? null : positiveInt(json[key]);
}

String requiredText(Object? value, {required int maxLength}) {
  if (value is! String ||
      value.trim().isEmpty ||
      value.runes.length > maxLength) {
    throw ApiFailure.protocol;
  }
  return value;
}

String? nullableText(
  Map<String, dynamic> json,
  String key, {
  required int maxLength,
}) {
  if (!json.containsKey(key)) throw ApiFailure.protocol;
  final value = json[key];
  if (value == null) return null;
  if (value is! String || value.runes.length > maxLength) {
    throw ApiFailure.protocol;
  }
  return value;
}

bool validCalendarDate(String value, {int minYear = 1000}) {
  if (value.length != 10 ||
      !RegExp(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$').hasMatch(value)) {
    return false;
  }
  final year = int.parse(value.substring(0, 4));
  final month = int.parse(value.substring(5, 7));
  final day = int.parse(value.substring(8, 10));
  if (year < minYear || month < 1 || month > 12 || day < 1 || day > 31) {
    return false;
  }
  final parsed = DateTime.utc(year, month, day);
  return parsed.year == year && parsed.month == month && parsed.day == day;
}

DateTime utcTimestamp(Object? value) {
  if (value is! String) throw ApiFailure.protocol;
  final match = RegExp(
    r'^([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$',
  ).firstMatch(value);
  if (match == null ||
      match.end != value.length ||
      !validCalendarDate(match.group(1)!, minYear: 1) ||
      int.parse(match.group(2)!) > 23 ||
      int.parse(match.group(3)!) > 59 ||
      int.parse(match.group(4)!) > 59) {
    throw ApiFailure.protocol;
  }
  final offset = match.group(5)!;
  if (offset != 'Z' &&
      (int.parse(offset.substring(1, 3)) > 23 ||
          int.parse(offset.substring(4, 6)) > 59)) {
    throw ApiFailure.protocol;
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw ApiFailure.protocol;
  return parsed.toUtc();
}

bool validBearer(String token) =>
    token.length == 43 && RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(token);
