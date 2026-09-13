from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from .forms import LandingInquiryForm
from .models import LandingInquiry

BRAND_CONTEXT = {
    'brand_name': 'InnVetrix',
    'tagline': 'Stay Ahead. Beyond Expectations.',
    'company_name': 'Ultoxy Technologies',
    'phone': '7776824564',
    'phone_display': '+91 77768 24564',
    'email': 'ultoxy.tech@gmail.com',
    'website': 'https://www.ultoxy.com',
    'whatsapp_url': 'https://wa.me/917776824564?text=Hello%20InnVetrix%20Team%2C%20I%20am%20interested%20in%20a%20free%20live%20demo%20for%20my%20property.',
    'portal_login_url': 'https://prameshwar4378.github.io/LMS-React/#/login',
    'year': timezone.now().year,
}

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def home_view(request):
    form = LandingInquiryForm()
    if request.method == 'POST':
        form = LandingInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip_address = get_client_ip(request)
            inquiry.save()
            messages.success(
                request,
                f"Thank you, {inquiry.full_name}! Your demo request for '{inquiry.property_name}' has been successfully scheduled. Our team will reach out at {inquiry.phone} within 15 minutes."
            )
            return redirect('home')
        else:
            messages.error(request, "Please verify the information entered in the form fields.")

    context = {
        **BRAND_CONTEXT,
        'page_title': 'InnVetrix | Next-Gen Cloud Lodge & Hotel Management System',
        'active_nav': 'home',
        'form': form,
    }
    return render(request, 'landing/index.html', context)

def features_view(request):
    context = {
        **BRAND_CONTEXT,
        'page_title': 'Features & Capabilities | InnVetrix Hospitality Cloud',
        'active_nav': 'features',
    }
    return render(request, 'landing/features.html', context)

def pricing_view(request):
    context = {
        **BRAND_CONTEXT,
        'page_title': 'Transparent & Predictable Pricing Plans | InnVetrix',
        'active_nav': 'pricing',
    }
    return render(request, 'landing/pricing.html', context)

def about_view(request):
    context = {
        **BRAND_CONTEXT,
        'page_title': 'About Us & Mission | Ultoxy Technologies & InnVetrix',
        'active_nav': 'about',
    }
    return render(request, 'landing/about.html', context)

def contact_view(request):
    form = LandingInquiryForm()
    if request.method == 'POST':
        form = LandingInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip_address = get_client_ip(request)
            inquiry.save()
            messages.success(
                request,
                f"Thank you, {inquiry.full_name}! Your message regarding '{inquiry.property_name}' has been received. Our hospitality consultant will contact you via phone ({inquiry.phone}) and email shortly."
            )
            return redirect('contact')
        else:
            messages.error(request, "Please correct the highlighted errors below before submitting.")

    context = {
        **BRAND_CONTEXT,
        'page_title': 'Contact Us & Schedule Live Demo | InnVetrix',
        'active_nav': 'contact',
        'form': form,
    }
    return render(request, 'landing/contact.html', context)

def sitemap_view(request):
    base_url = request.build_absolute_uri('/')[:-1]
    pages = [
        {'loc': f"{base_url}/", 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': f"{base_url}/features/", 'changefreq': 'weekly', 'priority': '0.9'},
        {'loc': f"{base_url}/pricing/", 'changefreq': 'weekly', 'priority': '0.9'},
        {'loc': f"{base_url}/about/", 'changefreq': 'monthly', 'priority': '0.8'},
        {'loc': f"{base_url}/contact/", 'changefreq': 'weekly', 'priority': '0.85'},
    ]
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    now_iso = timezone.now().strftime('%Y-%m-%d')
    for page in pages:
        xml_content += '  <url>\n'
        xml_content += f"    <loc>{page['loc']}</loc>\n"
        xml_content += f"    <lastmod>{now_iso}</lastmod>\n"
        xml_content += f"    <changefreq>{page['changefreq']}</changefreq>\n"
        xml_content += f"    <priority>{page['priority']}</priority>\n"
        xml_content += '  </url>\n'
    xml_content += '</urlset>'
    return HttpResponse(xml_content, content_type='application/xml')

def robots_view(request):
    base_url = request.build_absolute_uri('/')[:-1]
    content = f"""User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/

Sitemap: {base_url}/sitemap.xml
"""
    return HttpResponse(content, content_type='text/plain')
