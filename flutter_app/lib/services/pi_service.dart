import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/aruco_marker.dart';
import '../models/pi_status.dart';
import '../models/localization_result.dart';

class PiServiceException implements Exception {
  final String message;
  const PiServiceException(this.message);
  @override
  String toString() => message;
}

class PiService {
  final String baseUrl;
  final Duration timeout;

  PiService({required this.baseUrl, this.timeout = const Duration(seconds: 5)});

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Map<String, String> get _headers => {'Content-Type': 'application/json'};

  Future<PiStatus> checkStatus() async {
    try {
      final response =
          await http.get(_uri('/api/health')).timeout(timeout);
      if (response.statusCode == 200) {
        return PiStatus.fromJson(
            jsonDecode(response.body) as Map<String, dynamic>);
      }
      return PiStatus.offline();
    } catch (_) {
      return PiStatus.offline();
    }
  }

  Future<List<ArucoMarker>> getMarkers() async {
    try {
      final response =
          await http.get(_uri('/api/markers')).timeout(timeout);
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final list = data is Map ? (data['markers'] as List) : data as List;
        return list
            .map((e) => ArucoMarker.fromJson(e as Map<String, dynamic>))
            .toList();
      }
      throw PiServiceException(
          'Failed to fetch markers (${response.statusCode})');
    } on PiServiceException {
      rethrow;
    } catch (e) {
      throw PiServiceException('Connection error: $e');
    }
  }

  Future<void> sendCalibration(List<ArucoMarker> markers) async {
    try {
      final body =
          jsonEncode({'markers': markers.map((m) => m.toJson()).toList()});
      final response = await http
          .post(_uri('/api/markers'), headers: _headers, body: body)
          .timeout(timeout);
      if (response.statusCode != 200 && response.statusCode != 201) {
        throw PiServiceException(
            'Calibration upload failed (${response.statusCode})');
      }
    } on PiServiceException {
      rethrow;
    } catch (e) {
      throw PiServiceException('Connection error: $e');
    }
  }

  Future<void> clearMarkers() async {
    try {
      final response =
          await http.delete(_uri('/api/markers')).timeout(timeout);
      if (response.statusCode != 200 && response.statusCode != 204) {
        throw PiServiceException(
            'Failed to clear markers (${response.statusCode})');
      }
    } on PiServiceException {
      rethrow;
    } catch (e) {
      throw PiServiceException('Connection error: $e');
    }
  }

  Future<LocalizationResult?> getLocalization() async {
    try {
      final response =
          await http.get(_uri('/api/localization')).timeout(timeout);
      if (response.statusCode == 200) {
        return LocalizationResult.fromJson(
            jsonDecode(response.body) as Map<String, dynamic>);
      }
      if (response.statusCode == 204) return null;
      throw PiServiceException(
          'Localization request failed (${response.statusCode})');
    } on PiServiceException {
      rethrow;
    } catch (e) {
      throw PiServiceException('Connection error: $e');
    }
  }
}
