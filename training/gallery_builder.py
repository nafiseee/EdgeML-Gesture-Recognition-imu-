import base64
from io import BytesIO
import matplotlib.pyplot as plt

def build_gallery(df_source, output_html='gallery.html'):
    plt.style.use('dark_background')
    df = df_source.copy()
    
    axes = ['ax', 'ay', 'az', 'gx', 'gy', 'gz']
    for col in axes:
        df[col] = (df[col] - df[col].mean()) / (df[col].std() + 1e-6)
        
    labels = sorted(df['label'].unique())
    
    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Dataset Gallery</title>
    <style>
        body { background: #111; color: #fff; font-family: sans-serif; padding: 20px; }
        .tab-container { text-align: center; margin-bottom: 25px; }
        .tab-btn { background: #333; color: #fff; border: none; padding: 10px 20px; margin: 4px; border-radius: 8px; cursor: pointer; }
        .tab-btn.active { background: #f39c12; font-weight: bold; }
        .grid { display: none; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 15px; }
        .grid.active { display: grid; }
        .card { background: #222; border-radius: 8px; padding: 10px; text-align: center; }
        .id-label { font-size: 18px; font-weight: bold; color: #ff4757; margin-bottom: 5px; }
        img { max-width: 100%; border-radius: 4px; }
    </style>
    <script>
        function showClass(id) {
            document.querySelectorAll('.grid').forEach(e => e.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(e => e.classList.remove('active'));
            document.getElementById('grid-' + id).classList.add('active');
            document.getElementById('btn-' + id).classList.add('active');
        }
    </script></head><body><h2 style="text-align:center;">6DoF Dataset Inspector</h2><div class="tab-container">"""
    
    for lbl in labels:
        act = 'active' if lbl == labels[0] else ''
        html += f'<button id="btn-{lbl}" class="tab-btn {act}" onclick="showClass(\'{lbl}\')">Class {lbl}</button>'
    html += "</div>"
    
    for lbl in labels:
        c_df = df[df['label'] == lbl]
        act = 'active' if lbl == labels[0] else ''
        html += f'<div id="grid-{lbl}" class="grid {act}">'
        
        for gid, group in c_df.groupby('gesture_id'):
            fig, ax = plt.subplots(figsize=(3.5, 2.2))
            for col, color in zip(['ax', 'ay', 'az'], ['#ff4757', '#2ed573', '#1e90ff']):
                ax.plot(group[col].values, color=color, lw=1)
            for col, color in zip(['gx', 'gy', 'gz'], ['#ff4757', '#2ed573', '#1e90ff']):
                ax.plot(group[col].values, color=color, lw=1, ls='--')
            ax.axis('off')
            plt.tight_layout(pad=0.1)
            
            buf = BytesIO()
            plt.savefig(buf, format='png', facecolor='#222')
            plt.close(fig)
            b64 = base64.b64encode(buf.getbuffer()).decode("ascii")
            html += f'<div class="card"><div class="id-label">ID: {gid}</div><img src="data:image/png;base64,{b64}"></div>'
        html += "</div>"
        
    html += "</body></html>"
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html)