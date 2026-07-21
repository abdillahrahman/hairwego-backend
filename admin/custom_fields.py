import os
import uuid
import base64
from wtforms import fields, widgets
from markupsafe import Markup

class CropperWidget(widgets.FileInput):
    def __call__(self, field, **kwargs):
        input_id = kwargs.get('id', field.id)
        hidden_id = input_id + '_base64'
        preview_id = input_id + '_preview'
        modal_id = input_id + '_modal'
        
        filename_id = input_id + '_orig_filename'
        
        # Build HTML
        html = f'''
        <div class="cropper-wrapper" id="{input_id}_wrapper">
            <input type="file" id="{input_id}" accept="image/*" class="form-control-file">
            <textarea name="{field.name}" id="{hidden_id}" style="display:none;"></textarea>
            <input type="hidden" id="{filename_id}">
            
            <div style="margin-top: 10px;">
                <img id="{preview_id}" style="max-width: 100%; max-height: 200px; display: none;">
            </div>

            <!-- Modal for Cropper -->
            <div class="modal fade" id="{modal_id}" tabindex="-1" role="dialog" data-backdrop="static">
              <div class="modal-dialog modal-lg" role="document">
                <div class="modal-content">
                  <div class="modal-header">
                    <h5 class="modal-title">Crop Image</h5>
                    <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                      <span aria-hidden="true">&times;</span>
                    </button>
                  </div>
                  <div class="modal-body">
                    <div style="max-width: 100%; max-height: 70vh;">
                        <img id="{input_id}_cropper_img" style="max-width: 100%; display: block;">
                    </div>
                  </div>
                  <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" id="{input_id}_crop_btn">Crop & Save</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Scripts and Styles for Cropper.js -->
            <link href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css" rel="stylesheet">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>
            <script>
                document.addEventListener("DOMContentLoaded", function() {{
                    var fileInput = document.getElementById("{input_id}");
                    var hiddenInput = document.getElementById("{hidden_id}");
                    var previewImg = document.getElementById("{preview_id}");
                    var cropperImg = document.getElementById("{input_id}_cropper_img");
                    var cropBtn = document.getElementById("{input_id}_crop_btn");
                    
                    var cropper;
                    var modalElement = document.getElementById("{modal_id}");
                    
                    fileInput.addEventListener("change", function(e) {{
                        var files = e.target.files;
                        if (files && files.length > 0) {{
                            document.getElementById("{filename_id}").value = files[0].name;
                            var reader = new FileReader();
                            reader.onload = function(event) {{
                                cropperImg.src = event.target.result;
                                $('#{modal_id}').modal('show');
                            }};
                            reader.readAsDataURL(files[0]);
                        }}
                    }});

                    $('#{modal_id}').on('shown.bs.modal', function () {{
                        cropper = new Cropper(cropperImg, {{
                            aspectRatio: NaN, // free crop (no fixed ratio)
                            viewMode: 1,
                        }});
                    }}).on('hidden.bs.modal', function () {{
                        if (cropper) {{
                            cropper.destroy();
                            cropper = null;
                        }}
                        fileInput.value = ""; // clear file input so it can be re-selected if needed
                    }});

                    cropBtn.addEventListener("click", function() {{
                        if (!cropper) return;
                        var canvas = cropper.getCroppedCanvas();
                        var base64data = canvas.toDataURL("image/jpeg", 0.9);
                        var origName = document.getElementById("{filename_id}").value;
                        if (origName) {{
                            hiddenInput.value = origName + "|" + base64data;
                        }} else {{
                            hiddenInput.value = base64data;
                        }}
                        previewImg.src = base64data;
                        previewImg.style.display = "block";
                        $('#{modal_id}').modal('hide');
                    }});
                }});
            </script>
        </div>
        '''
        
        # Show existing image if edit mode
        current_val = field.data
        if isinstance(current_val, str) and current_val and not current_val.startswith('data:image'):
            # Need url_for here
            from flask import url_for
            filename = current_val.replace('static/uploads/', '')
            try:
                image_url = url_for('static', filename=f'uploads/{filename}')
                html += f'''
                <div style="margin-top: 10px;">
                    <p>Current Image:</p>
                    <img src="{image_url}" style="max-height: 100px;">
                </div>
                '''
            except Exception:
                pass
            
        return Markup(html)

class CropperImageField(fields.StringField):
    widget = CropperWidget()
    
    def __init__(self, label=None, validators=None, base_path='', relative_path='', namegen=None, **kwargs):
        super().__init__(label, validators, **kwargs)
        self.base_path = base_path
        self.relative_path = relative_path
        self.namegen = namegen
        self._temp_data = None
        self._temp_filename = None
        
    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            val = valuelist[0]
            if '|data:image/' in val:
                filename, base64data = val.split('|', 1)
                self._temp_filename = filename
                self._temp_data = base64data
            elif val.startswith('data:image/'):
                self._temp_filename = None
                self._temp_data = val
            else:
                self._temp_data = None
                self._temp_filename = None
        else:
            self._temp_data = None
            self._temp_filename = None
            
    def populate_obj(self, obj, name):
        if self._temp_data:
            val = self._temp_data
            header, encoded = val.split(",", 1)
            ext = 'jpg' if 'jpeg' in header else 'png'
            data = base64.b64decode(encoded)
            
            if self.namegen:
                filename = self.namegen(obj, self._temp_filename)
                if not os.path.splitext(filename)[1]:
                    filename += f".{ext}"
            elif self._temp_filename:
                # Use the original filename but we might want to sanitize it
                import werkzeug.utils
                filename = werkzeug.utils.secure_filename(self._temp_filename)
                # If there's no extension or it changed, maybe we should append it?
                # Usually it's fine as long as we secure it. 
                # Let's ensure it has an extension. If the crop is jpeg, let's just keep original extension.
                if not filename:
                    filename = f"crop_{uuid.uuid4().hex}.{ext}"
            else:
                filename = f"crop_{uuid.uuid4().hex}.{ext}"

            if self.relative_path.endswith('/'):
                rel_path = self.relative_path + filename
            else:
                rel_path = self.relative_path + '/' + filename
                
            full_path = os.path.join(self.base_path, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Handle duplicate filenames by appending _1, _2, etc.
            if os.path.exists(full_path):
                name_part, ext_part = os.path.splitext(filename)
                counter = 1
                while True:
                    new_filename = f"{name_part}_{counter}{ext_part}"
                    if self.relative_path.endswith('/'):
                        rel_path = self.relative_path + new_filename
                    else:
                        rel_path = self.relative_path + '/' + new_filename
                    full_path = os.path.join(self.base_path, rel_path)
                    if not os.path.exists(full_path):
                        break
                    counter += 1
            
            with open(full_path, "wb") as f:
                f.write(data)
                
            setattr(obj, name, rel_path)

