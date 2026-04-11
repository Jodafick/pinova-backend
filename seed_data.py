import os
import django
import requests
import random
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile

# Configurer Django pour le script
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')
django.setup()

from django.contrib.auth.models import User
from pins.models import Pin
from accounts.models import Profile

def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        img_temp = NamedTemporaryFile()
        img_temp.write(response.content)
        img_temp.flush()
        return img_temp
    return None

def seed_data():
    print("Mise à jour de la base de données...")
    # Ne pas supprimer les anciens pins, juste en ajouter
    # Pin.objects.all().delete()
    User.objects.exclude(is_superuser=True).delete()

    usernames = ['Clara', 'Leo', 'Aya', 'Max', 'Zoe', 'Nina', 'Emma', 'Karim', 'Sofia', 'Lucas']
    users = []
    
    # Créer l'admin si pas là
    admin, _ = User.objects.get_or_create(username='admin')
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

    topics = ['Maison et déco', 'Recettes faciles', 'Voyages', 'Inspiration design', 'Art & illustration', 'Plantes', 'Mode', 'Bien-être', 'Photographie', 'DIY & Crafts']
    
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
