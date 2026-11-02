import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Define locations and their corresponding two dates
LOCATIONS_DATES = {
    "indoor_Bharti501": ["20261006", "20261013"],
    "indoor_AzadApt": ["20261013", "20261015"],
    "indoor_BlueTokai": ["20261012", "20261013"],
    "indoor_Shubham_JiaSarai": ["20261017", "20261018"],
    "outdoor_Car": ["20261012", "20261013"],
    "outdoor_Ground": ["20261011", "20261012"],
    "outdoor_Rajdhani": ["20261012", "20261013"],
}

PAGE_WIDTH, PAGE_HEIGHT = letter

def draw_grid_page(c, plots_info, page_title):
    """
    Draws multiple graphs in a 2-column grid on a single page.
    plots_info is a list of tuples: (image_path, label)
    """
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, PAGE_HEIGHT - 35, page_title)
    
    cols = 2
    margin_x = 40
    margin_top = 55
    margin_bottom = 30
    available_w = PAGE_WIDTH - (2 * margin_x)
    available_h = PAGE_HEIGHT - margin_top - margin_bottom
    
    n = len(plots_info)
    rows = (n + cols - 1) // cols
    
    cell_w = available_w / cols - 15
    cell_h = available_h / rows - 15
    
    for idx, (img_path, label) in enumerate(plots_info):
        r = idx // cols
        col = idx % cols
        
        x = margin_x + col * (cell_w + 30)
        y = PAGE_HEIGHT - margin_top - (r + 1) * (cell_h + 15)
        
        # Draw label for the sub-graph
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y + cell_h + 3, label)
        
        if os.path.exists(img_path):
            try:
                img = ImageReader(img_path)
                img_w, img_h = img.getSize()
                scale = min(cell_w / img_w, (cell_h - 12) / img_h)
                d_w = img_w * scale
                d_h = img_h * scale
                
                # Center image inside its grid cell
                img_x = x + (cell_w - d_w) / 2
                img_y = y + (cell_h - 12 - d_h) / 2
                
                c.drawImage(img_path, img_x, img_y, width=d_w, height=d_h)
            except Exception as e:
                c.setFont("Helvetica", 7)
                c.drawString(x, y + cell_h / 2, "[Error loading image]")
        else:
            c.setFont("Helvetica", 7)
            c.drawString(x, y + cell_h / 2, f"[Missing: {os.path.basename(img_path)}]")
            
    c.showPage()

def build_pdf(test_type, direction, output_filename):
    """
    Builds a PDF workbook grouped by metric pages across all locations 
    for each of the two days.
    """
    c = canvas.Canvas(output_filename, pagesize=letter)
    print(f"Generating PDF: {output_filename}...")
    
    dir_short = direction.upper() # 'DL' or 'UL'
    
    # Repeat pipeline for two days (day index 0 and 1)
    for day_idx in range(2):
        day_label = f" (Day {day_idx + 1})"
        
        p1_plots, p2_plots, p3_plots, p4_plots, p5_plots = [], [], [], [], []
        p6_plots, p7_plots, p8_plots, p9_plots = [], [], [], []
        
        for loc, dates in LOCATIONS_DATES.items():
            date = dates[day_idx]  # Pulls the correct date for this location
            base_dir = f"graphs/{test_type}"
            direction_str = "downlink" if dir_short == "DL" else "uplink"
            # Page 1: Throughput Box Plots
            if test_type == "speedtest":
                p1_path = f"{base_dir}/Throughput_BoxPlots/{loc}/{date}_throughput.png"
                p2_path = f"graphs/speedtest/fallback_graphs/{loc}/{date}/{date}_{direction_str}_win1000ms_consolidated.png"
                p3_path = f"graphs/speedtest/Ratio_plots/{loc}/{date}_rsrp.png"
                p4_path = f"graphs/speedtest/Ratio_plots/{loc}/{date}_rsrq.png"
                p5_path = f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_rb_cdf_combined.png"
            else:
                p1_path = f"{base_dir}/BoxPlots/{loc}/{date}_throughput.png"
                p2_path = f"graphs/dummyVC/fallback_graphs/{loc}/{date}/{date}_{direction_str}_win1000ms_consolidated.png"
                p3_path = f"graphs/dummyVC/Ratio_plots/{loc}/{date}_rsrp.png"
                p4_path = f"graphs/dummyVC/Ratio_plots/{loc}/{date}_rsrq.png"
                p5_path = f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_rb_cdf_combined.png"
            p1_plots.append((p1_path, f"{loc} | {date}"))
            p2_plots.append((p2_path, f"{loc} | {date}"))
            # Page 3: RSRP            
            p3_plots.append((p3_path, f"{loc} | {date}"))
            # Page 4: RSRQ
            p4_plots.append((p4_path, f"{loc} | {date}"))
            # Page 5: Resource blocks Contribution
            p5_plots.append((p5_path, f"{loc} | {date}"))

            # QMDL Metrics
            if dir_short == "DL":
                if test_type == "speedtest":
                    p6_plots.append((f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_mimo_layers_5g.png", f"{loc} | {date}"))
                    p7_plots.append((f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_mimo_layers_4g.png", f"{loc} | {date}"))
                    p8_plots.append((f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_modulation_5g.png", f"{loc} | {date}"))
                    p9_plots.append((f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_modulation_4g.png", f"{loc} | {date}"))
                else:
                    p6_plots.append((f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_mimo_layers_5g.png", f"{loc} | {date}"))
                    p7_plots.append((f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_mimo_layers_4g.png", f"{loc} | {date}"))
                    p8_plots.append((f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_modulation_5g.png", f"{loc} | {date}"))
                    p9_plots.append((f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_DL_modulation_4g.png", f"{loc} | {date}"))
            else:
                if test_type == "speedtest":
                    p6_plots.append((f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_UL_modulation_5g.png", f"{loc} | {date}"))
                    p7_plots.append((f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_UL_modulation_4g.png", f"{loc} | {date}"))
                else:
                    p6_plots.append((f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_UL_modulation_5g.png", f"{loc} | {date}"))
                    p7_plots.append((f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_UL_modulation_4g.png", f"{loc} | {date}"))

        # Write out pages for this day
        draw_grid_page(c, p1_plots, f"Throughput Box Plots - {test_type.upper()}{day_label}")
        draw_grid_page(c, p2_plots, f"Fallback Plots ({dir_short}){day_label}")
        draw_grid_page(c, p3_plots, f"Coverage Metrics - RSRP{day_label}")
        draw_grid_page(c, p4_plots, f"Coverage Metrics - RSRQ{day_label}")
        draw_grid_page(c, p5_plots, f"Resource Blocks Contribution{day_label}")

        if dir_short == "DL":
            draw_grid_page(c, p6_plots, f"MIMO Layers 5G (DL){day_label}")
            draw_grid_page(c, p7_plots, f"MIMO Layers 4G (DL){day_label}")
            draw_grid_page(c, p8_plots, f"Modulation 5G (DL){day_label}")
            draw_grid_page(c, p9_plots, f"Modulation 4G (DL){day_label}")
        else:
            draw_grid_page(c, p6_plots, f"Modulation 5G (UL){day_label}")
            draw_grid_page(c, p7_plots, f"Modulation 4G (UL){day_label}")

    c.save()
    print(f"Successfully generated {output_filename}")

if __name__ == "__main__":
    configs = [
        ("speedtest", "DL", "graphs/workbook/speedtest_DL_workbook.pdf"),
        ("speedtest", "UL", "graphs/workbook/speedtest_UL_workbook.pdf"),
        ("dummyVC", "DL", "graphs/workbook/dummyVC_DL_workbook.pdf"),
        ("dummyVC", "UL", "graphs/workbook/dummyVC_UL_workbook.pdf"),
    ]

    for test_type, direction, filename in configs:
        build_pdf(test_type, direction, filename)