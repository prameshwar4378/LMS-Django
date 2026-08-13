from django.db import models

class Customer(models.Model):
    class IDType(models.TextChoices):
        AADHAAR = 'Aadhaar', 'Aadhaar'
        PAN = 'PAN', 'PAN'
        PASSPORT = 'Passport', 'Passport'
        DRIVING_LICENCE = 'Driving Licence', 'Driving Licence'
        VOTER_ID = 'Voter ID', 'Voter ID'
        OTHER = 'Other', 'Other'

    class Gender(models.TextChoices):
        MALE = 'Male', 'Male'
        FEMALE = 'Female', 'Female'
        OTHER = 'Other', 'Other'

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    mobile = models.CharField(max_length=20)
    alternate_mobile = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE)
    
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, default='India')
    nationality = models.CharField(max_length=100, default='Indian')
    occupation = models.CharField(max_length=100, blank=True, null=True)
    
    photo = models.ImageField(upload_to='customers/photos/', blank=True, null=True)
    id_type = models.CharField(max_length=50, choices=IDType.choices, default=IDType.AADHAAR)
    id_number = models.CharField(max_length=100, blank=True, null=True)
    id_document = models.FileField(upload_to='customers/documents/', blank=True, null=True)
    id_document_back = models.FileField(upload_to='customers/documents/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join([p for p in parts if p]).strip()

    def __str__(self):
        return f"{self.full_name} ({self.mobile})"

class CustomerDocument(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=200, default='Additional Document')
    document_file = models.FileField(upload_to='customers/documents/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.customer.full_name}"
