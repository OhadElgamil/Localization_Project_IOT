import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/pi_status.dart';
import '../services/pi_service.dart';

class ConnectionProvider extends ChangeNotifier {
  static const _keyHost = 'pi_host';
  static const _keyPort = 'pi_port';

  String _host = '192.168.1.100';
  int _port = 5000;
  PiStatus _status = PiStatus.offline();
  bool _isChecking = false;

  String get host => _host;
  int get port => _port;
  PiStatus get status => _status;
  bool get isChecking => _isChecking;
  bool get isConnected => _status.isOnline;
  String get baseUrl => 'http://$_host:$_port';

  PiService get service => PiService(baseUrl: baseUrl);

  ConnectionProvider() {
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
    _status = await service.checkStatus();
    _isChecking = false;
    notifyListeners();
    return _status.isOnline;
  }
}
