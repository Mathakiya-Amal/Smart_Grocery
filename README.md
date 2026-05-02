# 🥦 Smart Grocery - Instant Delivery Platform

Smart Grocery is a high-performance, full-stack instant grocery delivery application designed to provide a seamless shopping experience for customers while offering robust management tools for vendors and administrators. Built with a modern tech stack, it features AI-powered support, real-time analytics, and a premium "Emerald Enterprise" design system.

---

## 🌟 Key Features

### 🛒 Customer Interface
- **Modern Shopping Experience**: Intuitive product browsing with categorized grids and search autocomplete.
- **Smart Cart System**: Dynamic cart management with real-time price updates and free delivery threshold indicators.
- **Order Tracking**: Real-time progress timeline for orders (Pending → Confirmed → Shipped → Delivered).
- **Wishlist**: Save favorite items for future purchases.
- **AI Help Support**: Integrated LLaMA 3 chatbot to assist with order inquiries and platform navigation.

### 🏪 Vendor Dashboard
- **Store Management**: Add, edit, and manage product inventory and stock levels.
- **Revenue Analytics**: Interactive line charts (Chart.js) showing revenue trends over time (7d, 1m, 1y).
- **Order Processing**: Detailed sub-order management with a specialized progress flow for each item.
- **Product Badging**: Highlight products with "Sale", "New", or "Organic" badges.

### 🛡️ Admin Panel
- **System Overview**: High-level metrics for total customers, vendors, products, and platform-wide revenue.
- **User Management**: Control user roles (Customer, Vendor, Admin) and manage user account statuses (Block/Unblock).
- **Product Approval**: Review and approve/reject products listed by vendors before they go live.
- **Data Export**: Export revenue and order history to CSV for offline analysis.

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | Python (Flask) |
| **Database** | MongoDB (NoSQL) |
| **Frontend** | Tailwind CSS, JavaScript (Vanilla), Jinja2 |
| **Charts** | Chart.js |
| **AI** | LLaMA 3 (via local inference) |
| **Icons** | Google Material Symbols |

---

## 🎨 Design System: "Emerald Enterprise"

The project follows a unified design language that prioritizes readability, accessibility, and a premium aesthetic:
- **Primary Palette**: Emerald Green (#10B981) for a fresh, trustworthy feel.
- **Typography**: Work Sans (300-900 weights) for modern clarity.
- **Layouts**: High border-radius (2xl), soft shadows, and clean slate-based neutrals.
- **Theme**: Adaptive system (supports dark mode for dashboards).
- **Currency**: Fully localized to Indian Rupee (₹).

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- MongoDB instance (Local or Atlas)
- Ollama (for LLaMA 3 support)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/Smart-Grocery.git
   cd Smart-Grocery
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   Create a `.env` file or set the following variables:
   - `SECRET_KEY`: Your Flask secret key.
   - `MONGO_URI`: Your MongoDB connection string.

4. **Run the application**:
   ```bash
   python app.py
   ```

---

## 🏗️ Project Structure

```text
├── app.py              # Main Flask application logic
├── database.py         # MongoDB connection & initialization
├── recommender.py      # Recommendation engine logic
├── templates/          # Jinja2 HTML templates
├── static/             # CSS, JS, and image assets
└── stitch_login_signup/# Design assets and templates
```

---

## 📄 License

This project is for demonstration purposes. All rights reserved.

---

*Built with ❤️ for the future of grocery commerce.*
