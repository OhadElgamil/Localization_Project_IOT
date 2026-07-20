import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/optitrack_result.dart';

class OptiTrackServiceException implements Exception {
  final String message;
  const OptiTrackServiceException(this.message);
  @override
  String toString() => message;
}

class OptiTrackService {
  final String baseUrl;
  // Generous timeout: the server itself retries the flaky OptiTrack call
  // until it succeeds before responding, so a round trip can legitimately
  // take a while. This is a ceiling for the request to actually stop
  // waiting, not the expected duration.
  final Duration timeout;

  OptiTrackService({
    required this.baseUrl,
    this.timeout = const Duration(seconds: 60),
  });

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<bool> checkHealth() async {
    try {
      final response = await http
          .get(_uri('/api/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<OptiTrackResult> compare({
    required double x,
    required double y,
    required double z,
  }) async {
    try {
      final body = jsonEncode({
        'position': {'x': x, 'y': y, 'z': z},
      });
      final response = await http
          .post(
            _uri('/api/compare'),
            headers: {'Content-Type': 'application/json'},
            body: body,
          )
          .timeout(timeout);
      if (response.statusCode == 200) {
        return OptiTrackResult.fromJson(
            jsonDecode(response.body) as Map<String, dynamic>);
      }
      throw OptiTrackServiceException(
          'OptiTrack comparison failed (${response.statusCode})');
    } on OptiTrackServiceException {
      rethrow;
    } catch (e) {
      throw OptiTrackServiceException('Connection error: $e');
    }
  }
}
