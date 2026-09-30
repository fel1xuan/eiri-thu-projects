def configure_matplotlib_fonts():
    try:
        import matplotlib

        matplotlib.rcParams["font.sans-serif"] = [
            "Hiragino Sans GB",
            "Heiti SC",
            "Arial Unicode MS",
            "PingFang SC",
            "DejaVu Sans",
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass
