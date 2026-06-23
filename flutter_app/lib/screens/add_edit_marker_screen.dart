import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../models/aruco_marker.dart';
import '../providers/markers_provider.dart';

class AddEditMarkerScreen extends StatefulWidget {
  final ArucoMarker? existing;

  const AddEditMarkerScreen({super.key, this.existing});

  @override
  State<AddEditMarkerScreen> createState() => _AddEditMarkerScreenState();
}

class _AddEditMarkerScreenState extends State<AddEditMarkerScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _idCtrl;
  late final TextEditingController _xCtrl;
  late final TextEditingController _yCtrl;
  late final TextEditingController _zCtrl;

  bool get _isEditing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final m = widget.existing;
    _idCtrl = TextEditingController(text: m != null ? '${m.markerId}' : '');
    _xCtrl = TextEditingController(text: m != null ? '${m.x}' : '');
    _yCtrl = TextEditingController(text: m != null ? '${m.y}' : '');
    _zCtrl = TextEditingController(text: m != null ? '${m.z}' : '');
  }

  @override
  void dispose() {
    _idCtrl.dispose();
    _xCtrl.dispose();
    _yCtrl.dispose();
    _zCtrl.dispose();
    super.dispose();
  }

  void _save() {
    if (!_formKey.currentState!.validate()) return;

    final provider = context.read<MarkersProvider>();
    final markerId = int.parse(_idCtrl.text.trim());
    final x = double.parse(_xCtrl.text.trim());
    final y = double.parse(_yCtrl.text.trim());
    final z = double.parse(_zCtrl.text.trim());

    if (!_isEditing && provider.hasId(markerId)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Marker ID $markerId already exists.'),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
      return;
    }

    final marker = ArucoMarker(markerId: markerId, x: x, y: y, z: z);
    provider.addOrUpdateMarker(marker);
    Navigator.of(context).pop();
  }

  String? _validateDouble(String? v) {
    if (v == null || v.trim().isEmpty) return 'Required';
    if (double.tryParse(v.trim()) == null) return 'Enter a valid number';
    return null;
  }

  String? _validateId(String? v) {
    if (v == null || v.trim().isEmpty) return 'Required';
    final n = int.tryParse(v.trim());
    if (n == null) return 'Enter a valid integer';
    if (n < 0 || n > 1023) return 'ID must be 0–1023';
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? 'Edit Marker' : 'Add Marker'),
        backgroundColor: cs.primaryContainer,
        foregroundColor: cs.onPrimaryContainer,
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            _CoordField(
              controller: _idCtrl,
              label: 'Marker ID',
              hint: '0–1023',
              icon: Icons.tag,
              readOnly: _isEditing,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              validator: _validateId,
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 16),
            _buildSectionLabel(context, 'Position (meters)'),
            const SizedBox(height: 12),
            _CoordField(
              controller: _xCtrl,
              label: 'X',
              hint: 'e.g. 1.50',
              icon: Icons.arrow_right_alt,
              validator: _validateDouble,
            ),
            const SizedBox(height: 12),
            _CoordField(
              controller: _yCtrl,
              label: 'Y',
              hint: 'e.g. 0.00',
              icon: Icons.arrow_upward,
              validator: _validateDouble,
            ),
            const SizedBox(height: 12),
            _CoordField(
              controller: _zCtrl,
              label: 'Z',
              hint: 'e.g. 2.40',
              icon: Icons.height,
              validator: _validateDouble,
            ),
            const SizedBox(height: 32),
            FilledButton.icon(
              onPressed: _save,
              icon: const Icon(Icons.save),
              label: Text(_isEditing ? 'Update Marker' : 'Add Marker'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionLabel(BuildContext context, String text) {
    return Text(
      text,
      style: Theme.of(context).textTheme.labelLarge?.copyWith(
            color: Theme.of(context).colorScheme.primary,
          ),
    );
  }
}

class _CoordField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final IconData icon;
  final String? Function(String?)? validator;
  final bool readOnly;
  final List<TextInputFormatter>? inputFormatters;
  final TextInputType keyboardType;

  const _CoordField({
    required this.controller,
    required this.label,
    required this.hint,
    required this.icon,
    this.validator,
    this.readOnly = false,
    this.inputFormatters,
    this.keyboardType = const TextInputType.numberWithOptions(decimal: true, signed: true),
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      readOnly: readOnly,
      keyboardType: keyboardType,
      inputFormatters: inputFormatters,
      validator: validator,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: Icon(icon),
        border: const OutlineInputBorder(),
        filled: readOnly,
      ),
    );
  }
}
