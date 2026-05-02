import os
import django
import requests
import random
from pathlib import Path
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile

# Configurer Django pour le script
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')
django.setup()

from django.contrib.auth.models import User
from pins.models import Pin
from accounts.models import Profile
from django.conf import settings


def ensure_superuser():
    username = os.environ.get('SEED_SUPERUSER_USERNAME', 'admin')
    email = os.environ.get('SEED_SUPERUSER_EMAIL', 'admin@example.com')
    password = os.environ.get('SEED_SUPERUSER_PASSWORD', 'admin1234')

    superuser, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email},
    )
    if created:
        superuser.email = email
        superuser.is_staff = True
        superuser.is_superuser = True
        superuser.set_password(password)
        superuser.save()
        print(f"Superuser '{username}' créé.")
        return superuser

    if superuser.email != email:
        superuser.email = email
    if not superuser.is_staff:
        superuser.is_staff = True
    if not superuser.is_superuser:
        superuser.is_superuser = True

    # Toujours réaligner le mot de passe défini pour le seed.
    superuser.set_password(password)
    superuser.save()
    print(f"Superuser '{username}' mis à jour.")
    return superuser


def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        img_temp = NamedTemporaryFile()
        img_temp.write(response.content)
        img_temp.flush()
        return img_temp
    return None


def cleanup_existing_images():
    print("Suppression des images existantes...")

    # 1) Supprimer les fichiers liés aux pins existants
    for pin in Pin.objects.exclude(image='').iterator():
        if pin.image:
            pin.image.delete(save=False)

    # 2) Supprimer les enregistrements de pins (après suppression des fichiers)
    Pin.objects.all().delete()

    # 3) Nettoyer le dossier media/pins pour enlever tout fichier orphelin
    pins_dir = Path(settings.MEDIA_ROOT) / 'pins'
    if pins_dir.exists():
        for file_path in pins_dir.glob('*'):
            if file_path.is_file():
                file_path.unlink(missing_ok=True)

    print("Images existantes supprimées.")

def seed_data():
    print("Mise à jour de la base de données...")
    cleanup_existing_images()
    User.objects.exclude(is_superuser=True).delete()

    usernames = ['Clara', 'Leo', 'Aya', 'Max', 'Zoe', 'Nina', 'Emma', 'Karim', 'Sofia', 'Lucas']
    users = []
    
    # Créer/mette à jour le superuser admin
    admin = ensure_superuser()
    users.append(admin)

    print("Création des utilisateurs...")
    for name in usernames:
        user, created = User.objects.get_or_create(username=name.lower(), email=f"{name.lower()}@example.com")
        if created:
            user.set_password('password123')
            user.save()
            profile = user.profile
            profile.display_name = name
            profile.avatar_color = random.choice([
                'bg-amber-400', 'bg-emerald-400', 'bg-rose-400', 'bg-sky-400', 'bg-indigo-400', 'bg-lime-400',
                'bg-orange-400', 'bg-teal-400', 'bg-cyan-400', 'bg-violet-400', 'bg-fuchsia-400', 'bg-pink-400'
            ])
            profile.save()
        users.append(user)

    topics = [
        'Maison et déco', 'Recettes faciles', 'Voyages', 'Inspiration design', 'Art & illustration',
        'Plantes', 'Mode', 'Bien-être', 'Photographie', 'DIY & Crafts',
        'Technologie', 'Gaming setup', 'Business', 'Finance perso', 'Éducation',
        'Productivité', 'Architecture moderne', 'Street art', 'Cuisine africaine', 'Cuisine asiatique',
        'Desserts', 'Pâtisserie', 'Fitness', 'Yoga', 'Méditation',
        'Santé', 'Beauté', 'Coiffure', 'Mariage', 'Bébé & famille',
        'Animaux', 'Nature', 'Sports', 'Football', 'Basketball',
        'Musique', 'Cinéma', 'Séries', 'Lecture', 'Poésie',
        'Science', 'Astronomie', 'Automobile', 'Moto', 'Cyclisme',
        'Immobilier', 'Minimalisme', 'Rénovation', 'Jardinage', 'Écologie'
    ]
    
    image_queries = ['architecture', 'food', 'japan', 'workspace', 'tattoo', 'plants', 'baking', 'streetwear', 'yoga', 'colors', 'paris', 'macrame', 'nature', 'design', 'art', 'decor', 'kitchen', 'beach', 'mountain', 'city']
    
    print("Téléchargement des images et création de 500 Pins supplémentaires...")
    for i in range(100, 600):
        query = random.choice(image_queries)
        topic = random.choice(topics)
        
        img_url = f"https://picsum.photos/seed/{i}_{query}/600/900"
        
        temp_img = download_image(img_url)
        if temp_img:
            user = random.choice(users)
            pin = Pin.objects.create(
                title=f"Inspiration {query.capitalize()} {i+1}",
                description=f"Une superbe découverte sur le thème {query} pour votre catégorie {topic}.",
                author=user,
                topic=topic
            )
            pin.image.save(f"{query}_{i}.jpg", File(temp_img))
            print(f"[{i+1}/600] Pin '{pin.title}' ({topic}) créé par {user.username}")

    print("Données de test générées avec succès !")

if __name__ == "__main__":
    seed_data()
