# Five-minute synthetic BBO fixture

`synthetic_5min.csv` has 6,002 invented Binance/OKX quote rows from relative
millisecond 0 through 300,000 inclusive. It is not anonymized market data.
No live or registered-study tape was read. The generator deliberately inserts
follower responses and cannot demonstrate alpha. Sizes and spreads are invented.

`notebooks/build_walkthrough.py` generates the fixture and notebook. The notebook
embeds checksummed compressed copies of the fixture and exact cost-bridge source,
so it can run after downloading only the `.ipynb` file. The setup cell uses NumPy
and Matplotlib, installing them only if absent. GitHub renders saved outputs;
Colab can execute the notebook without exchange credentials or a repository clone.
