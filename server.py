from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import stripe  # You'll need to install stripe package
from functools import wraps
from flask_mail import Mail, Message
from flask_login import UserMixin, login_required, current_user, login_user, logout_user, LoginManager
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hotel_booking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-password'
db = "app.db"

mail = Mail(app)

db = SQLAlchemy(app)

# Add this after creating the Flask app instance
@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    if fmt is None:
        fmt = '%B %d, %Y'
    return date.strftime(fmt)
# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) 
# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password = db.Column(db.String(128))
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    bookings = db.relationship('Booking', backref='user', lazy='dynamic')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='user')  # user, admin, manager
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Hotel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    rooms = db.relationship('Room', backref='hotel', lazy='dynamic')

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    price_per_night = db.Column(db.Float, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    size = db.Column(db.Integer)  # in sq.ft
    bed_type = db.Column(db.String(50))
    total_rooms = db.Column(db.Integer, nullable=False, default=1)
    image_file = db.Column(db.String(20), nullable=False, default='room_default.jpg')
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotel.id'), nullable=False)
    bookings = db.relationship('Booking', backref='room', lazy='dynamic')

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    check_in_date = db.Column(db.DateTime, nullable=False)
    check_out_date = db.Column(db.DateTime, nullable=False)
    guests = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='confirmed')  # confirmed, checked_in, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)


class RoomAvailability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    price = db.Column(db.Float)
    
    __table_args__ = (db.UniqueConstraint('room_id', 'date'),)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotel.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('booking_id', 'user_id'),)

class SpecialRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotel.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    rate_multiplier = db.Column(db.Float, nullable=False)
    
    __table_args__ = (db.UniqueConstraint('hotel_id', 'start_date', 'end_date'),)

# Remove or comment out this decorator and function
# @app.before_first_request
# def create_tables():
#     db.create_all()

# Add these new functions instead


def init_db():
    with app.app_context():
        db.create_all()


@app.route('/')
def index():

    hotels = Hotel.query.all()
    now = datetime.now()
    return render_template('index.html', 
                         hotels=hotels, 
                         now=now, 
                         timedelta=timedelta)
 

@app.route('/search', methods=['GET'])
def search():
    # Extract query parameters
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    guests = int(request.args.get('guests', 1))
    children = int(request.args.get('children', 0))
    room_type = request.args.get('room_type')
    location = request.args.get('location', '')
    min_price = float(request.args.get('min_price', 0))
    max_price = float(request.args.get('max_price', 1000000))
    amenities = request.args.getlist('amenities')

    # Total guests = adults + children
    total_guests = guests + children

    # Filter hotels by location (if provided)
    hotel_query = Hotel.query
    if location:
        hotel_query = hotel_query.filter(Hotel.address.contains(location))

    hotels = hotel_query.all()

    # Filter rooms by capacity and price
    room_query = Room.query.filter(
        Room.capacity >= total_guests,
        Room.price.between(min_price, max_price)
    )

    # Filter by room type
    if room_type:
        room_query = room_query.filter(Room.room_type == room_type)

    # Filter by amenities
    if amenities:
        for amenity in amenities:
            room_query = room_query.filter(Room.amenities.contains(amenity))

    available_rooms = room_query.all()

    # Return partial results (for dynamic rendering)
    return render_template(
        'partials/room_results.html',
        rooms=available_rooms,
        hotels=hotels,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        children=children
    )
@app.route('/book/<int:hotel_id>', methods=['GET', 'POST'])
def book(hotel_id):
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        payment = request.form['payment']
        user_id = session.get('user_id')
        booking = Booking(hotel_id=hotel_id, user_id=user_id, name=name, contact=contact, payment=payment)
        db.session.add(booking)
        db.session.commit()
        flash("Booking successful!")
        return redirect(url_for('index'))
    hotel = Hotel.query.get_or_404(hotel_id)
    return render_template('book.html', hotel=hotel)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        # Use a safe, compatible hash method
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        user = User(username=username, password=hashed_password, email=email)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            # Generate password reset token and send email
            # This is a placeholder - implement actual email sending
            flash('Password reset instructions sent to your email')
        else:
            flash('Email not found')
    return render_template('forgot_password.html')

@app.route('/hotel/<int:hotel_id>')
def hotel_details(hotel_id):
    hotel = Hotel.query.get_or_404(hotel_id)
    rooms = Room.query.filter_by(hotel_id=hotel_id).all()
    return render_template('hotel_details.html', hotel=hotel, rooms=rooms)

@app.route('/book/<int:room_id>', methods=['POST'])
def create_booking(room_id):
    if not session.get('user_id'):
        return jsonify({'error': 'Please login first'}), 401
        
    data = request.get_json()
    check_in = datetime.strptime(data['check_in'], '%Y-%m-%d').date()
    check_out = datetime.strptime(data['check_out'], '%Y-%m-%d').date()
    
    # Check availability
    is_available = RoomAvailability.query.filter(
        RoomAvailability.room_id == room_id,
        RoomAvailability.date.between(check_in, check_out),
        RoomAvailability.is_available == True
    ).count() == (check_out - check_in).days
    
    if not is_available:
        return jsonify({'error': 'Room not available for selected dates'}), 400
        
    # Calculate total price
    room = Room.query.get_or_404(room_id)
    total_price = sum(
        room.get_price(check_in + timedelta(days=x))
        for x in range((check_out - check_in).days)
    )
    
    # Create Stripe payment intent
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(total_price * 100),  # Amount in cents
            currency='usd'
        )
        
        # Create booking
        booking = Booking(
            user_id=session['user_id'],
            room_id=room_id,
            check_in_date=check_in,
            check_out_date=check_out,
            total_price=total_price,
            num_guests=data['guests']
        )
        db.session.add(booking)
        db.session.commit()
        
        send_booking_confirmation(booking)
        
        return jsonify({
            'booking_id': booking.id,
            'client_secret': intent.client_secret
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/hotel/<int:hotel_id>/review', methods=['POST'])
def add_review():
    if not session.get('user_id'):
        return jsonify({'error': 'Please login first'}), 401
        
    data = request.get_json()
    booking = Booking.query.filter_by(
        hotel_id=hotel_id,
        user_id=session['user_id']
    ).first()
    
    if not booking:
        return jsonify({'error': 'You must have a booking to review'}), 400
        
    review = Review(
        hotel_id=hotel_id,
        user_id=session['user_id'],
        booking_id=booking.id,
        rating=data['rating'],
        comment=data['comment']
    )
    
    db.session.add(review)
    db.session.commit()
    
    # Update hotel rating
    hotel = Hotel.query.get(hotel_id)
    reviews = Review.query.filter_by(hotel_id=hotel_id).all()
    hotel.rating = sum(r.rating for r in reviews) / len(reviews)
    db.session.commit()
    
    return jsonify({'message': 'Review added successfully'})

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user', None)
    return redirect(url_for('index'))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = User.query.get(session.get('user_id'))
        if not user or not user.is_admin:
            flash('Admin access required')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@admin_required
def admin_dashboard():
    hotels = Hotel.query.all()
    bookings = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', hotels=hotels, bookings=bookings)

@app.route('/dashboard')
@login_required
def dashboard():
    # Get stats for dashboard
    total_bookings = Booking.query.count()
    revenue = db.session.query(db.func.sum(Booking.total_price)).scalar() or 0
    upcoming_checkins = Booking.query.filter(
        Booking.check_in_date >= datetime.now(),
        Booking.check_in_date <= datetime.now() + timedelta(days=1)
    ).count()
    
    # Get recent bookings
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    
    # Get room availability
    rooms = Room.query.all()
    room_availability = []
    for room in rooms:
        booked = Booking.query.filter(
            Booking.room_id == room.id,
            Booking.check_out_date >= datetime.now()
        ).count()
        available = room.total_rooms - booked
        room_availability.append({
            'type': room.type,
            'available': available,
            'total': room.total_rooms,
            'percentage': (booked / room.total_rooms) * 100 if room.total_rooms > 0 else 0
        })
    
    return render_template('dashboard.html',
                         total_bookings=total_bookings,
                         revenue=revenue,
                         upcoming_checkins=upcoming_checkins,
                         recent_bookings=recent_bookings,
                         room_availability=room_availability)
@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)
@app.route('/rooms')
@login_required
def rooms():
    rooms = Room.query.all()
    return render_template('rooms.html', rooms=rooms)

@app.route('/book/<int:room_id>', methods=['GET', 'POST'])
@login_required
def book_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    if request.method == 'POST':
        check_in = datetime.strptime(request.form['check_in'], '%Y-%m-%d')
        check_out = datetime.strptime(request.form['check_out'], '%Y-%m-%d')
        guests = int(request.form['guests'])
        
        # Check availability
        overlapping_bookings = Booking.query.filter(
            Booking.room_id == room_id,
            Booking.check_out_date > check_in,
            Booking.check_in_date < check_out
        ).count()
        
        if overlapping_bookings >= room.total_rooms:
            flash('No available rooms for selected dates', 'danger')
            return redirect(url_for('book_room', room_id=room_id))
        
        # Calculate total price
        nights = (check_out - check_in).days
        total_price = nights * room.price_per_night
        
        # Create booking
        booking = Booking(
            user_id=current_user.id,
            room_id=room_id,
            check_in_date=check_in,
            check_out_date=check_out,
            guests=guests,
            total_price=total_price,
            status='confirmed'
        )
        
        db.session.add(booking)
        db.session.commit()
        
        flash('Room booked successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('book.html', room=room)

@app.route('/my-bookings')
@login_required
def my_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
    return render_template('my_bookings.html', bookings=bookings)


@app.route('/admin/hotel/add', methods=['GET', 'POST'])
@admin_required
def add_hotel():
    if request.method == 'POST':
        hotel = Hotel(
            name=request.form['name'],
            address=request.form['address'],
            contact=request.form['contact'],
            description=request.form['description'],
            amenities=request.form['amenities'],
            image_url=request.form['image_url']
        )
        db.session.add(hotel)
        db.session.commit()
        flash('Hotel added successfully')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/hotel_form.html')

@app.route('/admin/room/<int:hotel_id>/add', methods=['GET', 'POST'])
@admin_required
def add_room(hotel_id):
    if request.method == 'POST':
        room = Room(
            hotel_id=hotel_id,
            type=request.form['type'],
            base_price=float(request.form['base_price']),
            weekend_price=float(request.form['weekend_price']),
            capacity=int(request.form['capacity']),
            description=request.form['description'],
            amenities=request.form['amenities'],
            max_guests=int(request.form['max_guests'])
        )
        db.session.add(room)
        db.session.commit()
        flash('Room added successfully')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/room_form.html', hotel_id=hotel_id)

@app.route('/admin/room/<int:room_id>/inventory', methods=['GET', 'POST'])
@admin_required
def manage_room_inventory(room_id):
    room = Room.query.get_or_404(room_id)
    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        price = float(request.form['price'])
        is_available = request.form.get('is_available', True)

        # Update or create availability records
        delta = end_date - start_date
        for i in range(delta.days + 1):
            date = start_date + timedelta(days=i)
            availability = RoomAvailability.query.filter_by(
                room_id=room_id, 
                date=date
            ).first()
            
            if availability:
                availability.price = price
                availability.is_available = is_available
            else:
                availability = RoomAvailability(
                    room_id=room_id,
                    date=date,
                    price=price,
                    is_available=is_available
                )
                db.session.add(availability)
        
        db.session.commit()
        flash('Room inventory updated successfully')
        return redirect(url_for('admin_dashboard'))
        
    return render_template('admin/room_inventory.html', room=room)

@app.route('/admin/hotel/<int:hotel_id>/special-rates', methods=['GET', 'POST'])
@admin_required
def manage_special_rates(hotel_id):
    if request.method == 'POST':
        special_rate = SpecialRate(
            hotel_id=hotel_id,
            name=request.form['name'],
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date(),
            rate_multiplier=float(request.form['rate_multiplier'])
        )
        db.session.add(special_rate)
        db.session.commit()
        flash('Special rate period added successfully')
        return redirect(url_for('admin_dashboard'))
        
    special_rates = SpecialRate.query.filter_by(hotel_id=hotel_id).all()
    return render_template('admin/special_rates.html', special_rates=special_rates)

@app.route('/admin/booking/<int:booking_id>/status', methods=['POST'])
@admin_required
def update_booking_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    status = request.form['status']
    if status in ['confirmed', 'cancelled']:
        booking.booking_status = status
        if status == 'cancelled':
            # Update room availability
            RoomAvailability.query.filter(
                RoomAvailability.room_id == booking.room_id,
                RoomAvailability.date.between(
                    booking.check_in_date,
                    booking.check_out_date
                )
            ).update({'is_available': True})
            db.session.commit()
        flash(f'Booking {status} successfully')
        db.session.commit()
    return redirect(url_for('manage_bookings'))

@app.route('/admin/bookings')
@admin_required
def manage_bookings():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)

@app.route('/admin/reports')
@admin_required
def view_reports():
    # Overall statistics
    total_bookings = Booking.query.count()
    total_revenue = db.session.query(db.func.sum(Booking.total_price)).scalar() or 0
    
    # Monthly statistics
    month_start = datetime.now().replace(day=1)
    monthly_bookings = Booking.query.filter(
        Booking.created_at >= month_start
    ).count()
    monthly_revenue = db.session.query(
        db.func.sum(Booking.total_price)
    ).filter(Booking.created_at >= month_start).scalar() or 0
    
    # Room occupancy rates
    rooms = Room.query.all()
    occupancy_rates = {}
    for room in rooms:
        total_days = (datetime.now() - room.created_at).days
        booked_days = Booking.query.filter_by(room_id=room.id).count()
        occupancy_rates[room.id] = (booked_days / total_days * 100) if total_days > 0 else 0
    
    return render_template(
        'admin/reports.html',
        total_bookings=total_bookings,
        total_revenue=total_revenue,
        monthly_bookings=monthly_bookings,
        monthly_revenue=monthly_revenue,
        occupancy_rates=occupancy_rates
    )

def send_booking_confirmation(booking):
    msg = Message(
        'Booking Confirmation',
        sender='your-email@gmail.com',
        recipients=[booking.user.email]
    )
    msg.body = f"""
    Dear {booking.name},
    
    Your booking has been confirmed:
    Hotel: {booking.hotel.name}
    Check-in: {booking.check_in_date}
    Check-out: {booking.check_out_date}
    Total Price: ${booking.total_price}
    
    Thank you for choosing our hotel!
    """
    mail.send(msg)
@app.route("/db")
def database():
    with app.app_context():
        db.drop_all()
        db.create_all()
    return "Database created successfully!"
# Modify the main block
if __name__ == '__main__':
    init_db()  # Initialize database before running the app
    app.run(debug=True)