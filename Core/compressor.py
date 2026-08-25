import os
import shutil
import logging
import subprocess
from Core.commons import colprint

logger = logging.getLogger()


def detect_best_encoder(codec='hevc') -> str:
    '''
    Detect the fastest available hardware or software encoder for the specified codec.
    '''
    try:
        out = subprocess.check_output(['ffmpeg', '-encoders'], stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
    except Exception:
        return 'libx265' if codec == 'hevc' else ('libsvtav1' if codec == 'av1' else 'libx264')

    if codec == 'hevc':
        if 'hevc_nvenc' in out:
            return 'hevc_nvenc'
        elif 'hevc_vaapi' in out and os.path.exists('/dev/dri/renderD128'):
            return 'hevc_vaapi'
        elif 'hevc_qsv' in out:
            return 'hevc_qsv'
        elif 'hevc_amf' in out:
            return 'hevc_amf'
        return 'libx265'
    elif codec == 'av1':
        if 'av1_nvenc' in out:
            return 'av1_nvenc'
        elif 'av1_qsv' in out:
            return 'av1_qsv'
        elif 'av1_vaapi' in out and os.path.exists('/dev/dri/renderD128'):
            return 'av1_vaapi'
        elif 'libsvtav1' in out:
            return 'libsvtav1'
        return 'libaom-av1'
    else:
        if 'h264_nvenc' in out:
            return 'h264_nvenc'
        elif 'h264_vaapi' in out and os.path.exists('/dev/dri/renderD128'):
            return 'h264_vaapi'
        return 'libx264'


def compress_video(input_path: str, output_path: str = None, codec: str = 'hevc', crf: int = 23, preset: str = 'slow') -> bool:
    '''
    Compress a video file using FFmpeg with hardware acceleration fallback.
    Re-encodes video with high-efficiency codec while copying audio/subtitle streams intact.
    '''
    if not input_path or not os.path.isfile(input_path):
        logger.warning(f"Compression target file not found: '{input_path}'")
        return False

    encoder = detect_best_encoder(codec)
    temp_output = f"{input_path}.compress.tmp.mkv"
    orig_size = os.path.getsize(input_path)

    colprint('header', f"\n⚡ Compressing '{os.path.basename(input_path)}' using {encoder.upper()} (CRF {crf})...")

    cmd = ['ffmpeg', '-y', '-i', input_path]

    if 'nvenc' in encoder:
        cmd.extend(['-c:v', encoder, '-preset', 'p5', '-cq', str(crf), '-b:v', '0'])
    elif 'vaapi' in encoder:
        cmd.extend(['-vaapi_device', '/dev/dri/renderD128', '-vf', 'format=nv12,hwupload', '-c:v', encoder, '-qp', str(crf)])
    elif 'qsv' in encoder:
        cmd.extend(['-c:v', encoder, '-global_quality', str(crf)])
    else:
        # Software encoder (libx265 / libsvtav1 / libx264)
        cmd.extend(['-c:v', encoder, '-crf', str(crf), '-preset', preset])

    # Copy audio and subtitles directly without re-compression
    cmd.extend(['-c:a', 'copy', '-c:s', 'copy', temp_output])

    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if res.returncode != 0 or not os.path.isfile(temp_output) or os.path.getsize(temp_output) == 0:
            err_msg = res.stderr.decode('utf-8', errors='ignore') if res.stderr else 'Unknown FFmpeg error'
            logger.warning(f"Hardware/optimized compression with {encoder} failed: {err_msg[:200]}")
            
            # Fallback to software libx265 if hardware encoder failed
            if encoder != 'libx265':
                logger.info("Retrying with software libx265 fallback...")
                cmd_fallback = ['ffmpeg', '-y', '-i', input_path, '-c:v', 'libx265', '-crf', str(crf), '-preset', preset, '-c:a', 'copy', '-c:s', 'copy', temp_output]
                res_fb = subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                if res_fb.returncode != 0 or not os.path.isfile(temp_output):
                    if os.path.exists(temp_output):
                        os.remove(temp_output)
                    return False

        new_size = os.path.getsize(temp_output)
        
        # Only replace if compressed file is smaller or valid
        if new_size < orig_size:
            final_target = output_path or input_path
            shutil.move(temp_output, final_target)
            saved_pct = int(((orig_size - new_size) / orig_size) * 100)
            orig_mb = orig_size / (1024 * 1024)
            new_mb = new_size / (1024 * 1024)
            colprint('success', f"  ✔ Compressed: {orig_mb:.1f} MB ➜ {new_mb:.1f} MB ({saved_pct}% disk space saved!)\n")
            return True
        else:
            # If original was already smaller than re-encoded output, keep original
            os.remove(temp_output)
            colprint('results', f"  ℹ Original file was already optimally compressed ({orig_size / (1024*1024):.1f} MB). Kept original.\n")
            return True

    except Exception as e:
        logger.error(f"Compression error on '{input_path}': {e}")
        if os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except Exception:
                pass
        return False
