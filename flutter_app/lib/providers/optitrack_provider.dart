import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/optitrack_service.dart';

class OptiTrackProvider extends ChangeNotifier {
  static const _keyHost = 'optitrack_host';
  static const _keyPort = 'optitrack_port';

  String _host = '192.168.1.101';
  int _port = 5002; // optitrack_server/server.py -- see its __main__ for the port split rationale
  bool _isOnline = false;
  bool _isChecking = false;

  String get host => _host;
  int get port => _port;
  bool get isOnline => _isOnline;
  bool get isChecking => _isChecking;
  String get baseUrl => 'http://$_host:$_port';

  OptiTrackService get service => OptiTrackService(baseUrl: baseUrl);

  OptiTrackProvider() {
    _loadPreferences();
  }

  Future<void> _loadPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    _host = prefs.getString(_keyHost) ?? _host;
    _port = prefs.getInt(_keyPort) ?? _port;
    notifyListeners();
  }

  Future<void> updateConnection(String host, int port) async {
    _host = host;
    _port = port;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyHost, host);
    await prefs.setInt(_keyPort, port);
    notifyListeners();
    await checkConnection();
  }

  Future<bool> checkConnection() async {
    _isChecking = true;
    notifyListeners();
    _isOnline = await service.checkHealth();
    _isChecking = false;
    notifyListeners();
    return _isOnline;
  }
}
