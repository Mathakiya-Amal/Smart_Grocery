from pymongo import MongoClient
import os

MONGO_URI = "mongodb+srv://Smart_Grocery:Smart_Grocery%40123@cluster0.te1scgp.mongodb.net/?appName=Cluster0"
DB_NAME = "smartgrocery"

# Store the client globally so we don't open too many connections
_client = None

import certifi
import ssl

def get_db():
    global _client
    if _client is None:
        # Standard secure connection using certifi for certificate validation
        _client = MongoClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000
        )
    return _client[DB_NAME]

PRODUCTS = [
    (1, "Fresh Organic Broccoli", "Veggies Pro", "Fresh Produce", 3.99, 4.50, "500g", "https://lh3.googleusercontent.com/aida-public/AB6AXuAWPwiQZlgx1qhrGzqGQWVsQEGIdGS-1onZR-1bmQfN1mbqtIiHweyl9gem3oDrf-n-VKtOgC_Pa3zRNDLdNTKO9YC6wWphZEO1tHdXqRTdv_iuqSPxo8GqHAgavfy9l6rj2Jhx14FlhTHRyHoI-lBK-41YdbOKAUVliZ5x1Qh9u6G766DjpySR1vQ7ws1fWRg7rCSJl1YuLNZphE64X2Cued_qQ0AJBId8k7XS8P2ALHP71z7x94viN-5CcCwAhMlVZss5vVo_4Q", "Organic"),
    (2, "Sweet Golden Pineapple", "Tropical Fresh", "Fresh Produce", 4.25, None, "1 unit (approx. 1.2kg)", "https://lh3.googleusercontent.com/aida-public/AB6AXuByhn0SMBhH6bHDIVBbnUCgbzTydmpdqNrdulYqclHcwLoMfnF0n8R4iUbGuPZhwm5VCf9B6DImsCRMUA7ytXSF-mS9EUUR7NuJDR56iaKpghpWLRji1GNWtP_RbMTGgB35JSPpka_0Pd-va34c7dUcASzK8tGyP8yZtwunCvWIFKf_F3pLXY6qb9Gb4HF7Co1HXZ4mMY6HY3N-yHp0qmuesa-1icO7LFaU7mDiHX0RTOlFprVXpxvCVATbdPTr9jhkEry-hC4VeA", None),
    (3, "Red Vine Tomatoes", "Local Farm", "Fresh Produce", 2.90, None, "1kg bag", "https://lh3.googleusercontent.com/aida-public/AB6AXuDSKS-F7JBNoeE9h-n1Q4n_vbWpxvaonJwBugGbH8Ge_pj5yqsug6ukSYmXQDde_C6Iwwzt_0b4gej3mXjYvxuQeo2p_bm6FmeTJZ1_WcDGVNBIaRvF1SEzVcAFlef7DX19BsJ50pbY4YUcNGg1rVlLgpMjndq1pb60M9nWOQ1z-ul6OEEJD8JtEzEIZPUxhqf2rzhvs99iUQZBUiyYcpnFshEyGJiSEjuwSYvqRjtx-qBp2dIxNCBXC3OAKERaMZqsIgKTJPRepQ", None),
    (4, "Crispy Spring Carrots", "Earth's Best", "Fresh Produce", 1.80, None, "500g bunch", "https://lh3.googleusercontent.com/aida-public/AB6AXuBG9ZAMU6-II5asnynKEhv_9m04hzwCXpDyFfuxqsWenKLiJMclqyj-hrcEF9Dbl4_JHHRGDnaSOatA24fDCQ89WQPbwAyw3YsFpVkQoTxdo_38dGDjlMmv0sOF_2x2oJr1cDyh1NSst38Uxjc2ls2iucukPx4x0-3CpuvIWRhTnAicwkcEMC7o613CtDtvCLQzpk8bo2PbKS1hhQtedOzXzuzS1YfZzCW55HuLnXanfycU9fHRvgDeHo1wFkHCDrW8mgPHDIY7MQ", "New"),
    (5, "Hass Avocados", "Local Farm", "Fresh Produce", 5.50, None, "2 units", "https://lh3.googleusercontent.com/aida-public/AB6AXuCW3QUwOkIs0pnG7gyrgm-xLsJOC1C_YoWjTH8jILNJecUj5oWB0IH1Wb6ISafFmIBQOupZi41hh6iF2CEk9vllCIltGsCIrDu555Pc0ziGKoeMZ_1zlScnK7NyeDlMcd55ZhJuO2WBTQ3FDJBULU6VZFSEsTTvr7637WTLQNdCw9s3gHUp5MHBkGpN5HT36moH_nFA3YZx12-6LqZh0xaGtAiHj9x8aBEsHBxxxrbyzLNt_P7jB8d_dcQtExdJ7OkliCsQoE3adA", None),
    (6, "Mixed Salad Greens", "Green Leaf", "Fresh Produce", 3.20, None, "250g pack", "https://lh3.googleusercontent.com/aida-public/AB6AXuCzHde_p3CePL4rSDPMNLj2_xw1gPbBWr6mmLYfMe6zUNPHSc0OgoPQ5cimZ27l37fJeehv5rXEj8vpZSwUYqKM40Pg8EAh9elF0Vf2aFK38feLL_bDfr9EFZmaaWn4dUwRZFmv79z4mtOt-sygT0iwaMV_g47k5mjwHsin6gEnxFg9jWmGkwsg4SH4lRipmrTacf6AVs6UfQwlUccEPa4FejRk8ctyIV3KznRhEDPjZTo-LNkWoi-7_5P6x3zNyCjFyUcfKuy9Ew", None),
    (7, "Sweet Garden Strawberries", "Berry Best", "Fresh Produce", 4.99, 6.50, "400g pack", "https://lh3.googleusercontent.com/aida-public/AB6AXuBFLnU4IU1A3VZ2vewNsiHu05Ujfj0deDp6gsytR5jhYl4jvqxo3L_Ny0GTZMsBLPue2SDxIqPshmWU0ILQ8vlusgfJpz523uLOJQDwyyFW1ePCN0CyODTvB5WoCKKnosPhXuf6lDx8kNtTbeJtoJ46pbx3T-taSscOvymUbgwiafyOTSiV5c4stobpgEwE0X-3HRJNki-FCGm5MieAHbi4Hn9VCC7uHj29MEpN77WQu3rUvn8rte_n7Lab4Nx_XqlxrfRW2aCqJg", "Sale"),
    (8, "Royal Gala Apples", "Nature's Pick", "Fresh Produce", 3.75, None, "1.5kg bag", "https://lh3.googleusercontent.com/aida-public/AB6AXuCIA-j_CB7rXwRX2GmJeKMGG84qpQljdGwphFZAsUpVj9HmNDtmSORK4-mqG9jEtCuhtMpGmGqiDH4Jj9-m3D2iduGA3eXbaAXTNWphNlJB9ZA8QvzpM5DlVD6wgbSBl-mYW4ZZIAU7mAdwaDd6kyXEASXIMxoef9TAXPpbek9VO4TIoVoYycKE1jIevna1jsPW_BvuX2tZCwt0oi4Ulk4hCk3sq_xv0RGBe_iZqBCkZwz9EWT5x8i-m0sNUylhCOobveZTQ7YHfQ", None),
    (9, "Fresh Organic Bananas", "Tropical Fresh", "Bakery", 2.99, None, "1kg Bundle", "https://lh3.googleusercontent.com/aida-public/AB6AXuCScwWfbmXLFGMdUNKVfh-QyQpVkv0pbKsWjPK61LwhcDZv210VxyxvbQ9eVFewXVz4E8Xx-k0-cCo5vMTsyrooARWL7CporpXsKOsr8eGNhRkv84K_VTtj8ZncjgPFjoJVjdwIzNPOWGWC1aGAOjV6EZs8NXt4m_4VoUxpN4DaEgMl9WUyWmQKA1rOv5uQjfuGOxxvJoZb72AvNRRCXixtUG2hu3nr7CpaCT-Xi_82ctU0NsqXYhtc7GCltP3Xb8xurkNy5-JG7A", None),
    (10, "Whole Wheat Bread", "Artisan Bakery", "Bakery", 5.50, None, "Artisan Sliced 400g", "https://lh3.googleusercontent.com/aida-public/AB6AXuDjFTw8BUVUml1Iv3htz9-8JauZqa_k2PLO71b_dfGvYPe6wnBF5QqnwY0wmbJVY_Ibp66ssYm1T6krEpXurfaOviytdskNtPyJ3SZr_SM9PM-wAPx8lZrp5NQI-uvTUskzvBtnf8aFC1bkHuDDi_PCv5CFUX9fVcoqTcfpZNBtWhgtcFxVUOaQtOTgavAKF8TH-l2AssA91Kzl4gZo2eHiF-8DM1ZpoV1eOU4OTW9tGiFlieKXR63TY8lRDfN63BTqRaApuwJO4Q", None),
    (11, "Almond Milk 1L", "Dairy Alternative", "Dairy & Eggs", 4.25, None, "Unsweetened, Vanilla", "https://lh3.googleusercontent.com/aida-public/AB6AXuAQ09S_WD5sBHmiab84QTH3jFRdv3TBl5YKj-SW7o50V7HlhVDykdGLmKgMGMplFXFMvF767YdNwDY0PQyd0tNNOGw_6Vp6sfJWVGHhOLxYjqFEVSsbdC9zOXYjc2nxbX9jH34V8fb_-SSrOYZYeV8yBhXLXKTKz7qRneOdduWqCXRyB6qV6mKOXssU28bru078XwT72F6fTp2kaeiLxWbWMjIWwBypS-kGGZ-_RaOP2u_HWKi8lcKLJo0pzbifN8FncQhJd3-Y4A", None),
    (12, "Organic Free Range Eggs", "Local Farm", "Dairy & Eggs", 6.99, None, "12 pack", "https://lh3.googleusercontent.com/aida-public/AB6AXuCKaLLkLwqm_FvjNnKG8MNwPAsxeTcR4N_lwikX4pRvsuMav0p3h87uIOL1LyAfrj6uT9VUZ_CjEgr7dLqWp4A_fJwcJR2_N-gUQYX_0uTCU7dnQTzdQhj72o_Atod_PrTj1_LpCHlVG5JrEb-gfK1uZh5hbYF8T2_bHe2AAJq0BfCC54sPKyZTH_yphYJmud0nOFCIVXCUN-M_xEYceagGtpZEQeoYbKz-5dEM35Wn_F-Jxl1dvOG1djUsPdRVS5LWRc2dw7VvDA", "Organic"),
    (13, "Wild Atlantic Salmon", "Ocean Fresh", "Meat & Seafood", 12.99, 15.99, "400g fillet", "https://lh3.googleusercontent.com/aida-public/AB6AXuBE-NxiStlvIdaNJHti9XRQ_NwFtfxOwB5IkJTQoH-gNevjs2UtMJQ5XoY8yOetVu4GvSsSXdJhUOaYz_Zu6fKAGC1xEmDSbdjwL-uR7Pr3IrUH71lQTPnYWae_R_PS1-IEUO6og_1iq9Yofqdx-IfqYUgA3b9J1rJEa2Sl9wnmJKnJXni36mZ7g1dsyw4ONbEezQeUCdPliQfnQODMxxcQAciWwh6xCTEU2h1tb766UOqWK3W2eaVA_Wy-B6ocJcuU_GPH6O5PzA", "Sale"),
    (14, "Extra Virgin Olive Oil", "Mediterranean", "Pantry Staples", 9.99, None, "750ml bottle", "https://lh3.googleusercontent.com/aida-public/AB6AXuCWKmSQ62n1eN_f9uvzLXmJdHk_9G3DGYFXHxaJB8pT6oMXP267QJ2vbOWfbrfIVdurWW2XeY64VSsdYyn4ADzljGqMnevFdWlS4hS7OdlGxiUs4LrvjEGvgCnSAabsYX29psl-S9OXo4TJgP-MwWeRwv7dfrK8I1SCWNOlB_qMg9QsvuLGO2E5nIKVkK9xDkqiOZOWUv6iMGJ2xyFfRmNapJh8U8eJhX22opT2NSWHMzbKRyeWEf4erOUZkqMn0aXkmWBNKUsrhw", None),
    (15, "Greek Yogurt", "Dairy Best", "Dairy & Eggs", 3.50, None, "500g tub", "https://lh3.googleusercontent.com/aida-public/AB6AXuA-MZ3NYaG5OU58-sg6AUmBwtv8q1DddfSy2tngf-OffM6-HRp2WHOBn2GG_TrrvIdCIzP2XlBX-V8jF2dY3rfH8nkfKsxnPFTN6IHgQkmBlo_np0rhJCq9X89rHSsS1UwmNVHrPp_kqDrhR2CEgXSrTv-nNsvx3y5Kf07MiSTIOS1KiLNDdEdhcMKU4O4_wnqeDtcdQPgKdwyebXBelh1y655kSZnvwi0Tos5MB_hqw-Ev3G9zwiL_1cWQ89176cXI0ozvlXqJsg", None),
    (16, "Sourdough Bread Loaf", "Artisan Bakery", "Bakery", 7.50, None, "800g loaf", "https://lh3.googleusercontent.com/aida-public/AB6AXuDTtRSs1inJbJWRAGONYFJrCFH9N2gGQeOxQeQARus3BdVigDLWghAOd1afRRx46nmOykkTLPSQMDQLJJ-bGLQFUPypwyTUrUiP6hfJH8G5gg7Eu_hiNwmahZSvV_hB5l_yFojK5SAgw5Rz9P7K1j5zhtguUCvbjG3bZ619lkRsOIWGhKMPl4rKesZ7wgjsQG6pRdx6nBrtnBuhsW1xr5DgbqAlV9yM1e_GkJshB0IITwpUJDIwjGqfd_VPj5Q4UfY9e-EOKpw9uA", None),
]

def init_db():
    db = get_db()
    products_col = db["products"]
    
    # If the collection is empty, insert the default products
    if products_col.count_documents({}) == 0:
        docs = []
        for p in PRODUCTS:
            docs.append({
                "_id": p[0],
                "name": p[1],
                "brand": p[2],
                "category": p[3],
                "price": p[4],
                "original_price": p[5],
                "unit": p[6],
                "image_url": p[7],
                "badge": p[8],
                "vendor_id": None,
                "is_approved": 1,
                "stock": 100
            })
        products_col.insert_many(docs)
