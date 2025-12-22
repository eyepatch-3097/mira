from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from landing.tracking import log_pageview
from .forms import WebsiteSourceCreateForm
from .models import DataSource, DataSourcePage
from .services.url_safety import normalize_domain_url
from .services.discover import discover_urls
from .services.categorize import categorize_url

@login_required
def sources_list(request):
    log_pageview(request, path="/sources/")
    sources = DataSource.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "sources/sources_list.html", {"sources": sources})

@login_required
def source_detail(request, source_id: int):
    src = get_object_or_404(DataSource, pk=source_id, user=request.user)
    log_pageview(request, path=f"/sources/{source_id}/")

    pages = src.pages.order_by("category", "url")[:500]  # cap UI
    return render(request, "sources/source_detail.html", {"src": src, "pages": pages})

@login_required
def source_progress(request, source_id: int):
    src = get_object_or_404(DataSource, pk=source_id, user=request.user)
    return JsonResponse({
        "status": src.status,
        "processed": src.processed_pages,
        "total": src.selected_pages,
        "error": src.error_message,
    })

@login_required
def website_source_new(request):
    log_pageview(request, path="/data-sources/website/new/")
    if request.method == "POST":
        form = WebsiteSourceCreateForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"].strip()
            raw_domain = form.cleaned_data["domain_url"].strip()

            try:
                domain_url = normalize_domain_url(raw_domain)
            except Exception as e:
                messages.error(request, str(e))
                return render(request, "sources/website_new.html", {"form": form})

            src = DataSource.objects.create(
                user=request.user,
                name=name,
                source_type="website",
                domain_url=domain_url,
                status="draft",
            )

            # Discover URLs now (fast enough). If you want async later, we’ll job this too.
            urls = discover_urls(domain_url, max_urls=300)

            if not urls:
                src.status = "failed"
                src.error_message = "Could not discover any URLs from this website."
                src.save(update_fields=["status", "error_message"])
                messages.error(request, "We couldn’t scrape this website. Try Documents / Custom Info instead.")
                return redirect("/data-sources/")

            pages = []
            for u in urls:
                pages.append(DataSourcePage(
                    source=src,
                    url=u,
                    category=categorize_url(u),
                    selected=True,
                    status="pending",
                ))
            DataSourcePage.objects.bulk_create(pages, ignore_conflicts=True)

            src.total_pages = src.pages.count()
            src.selected_pages = src.pages.filter(selected=True).count()
            src.save(update_fields=["total_pages", "selected_pages"])

            return redirect(f"/data-sources/website/{src.id}/pages/")

    else:
        form = WebsiteSourceCreateForm()
    return render(request, "sources/website_new.html", {"form": form})

@login_required
def website_pages_select(request, source_id: int):
    src = get_object_or_404(DataSource, pk=source_id, user=request.user, source_type="website")
    log_pageview(request, path=f"/data-sources/website/{source_id}/pages/")

    q = (request.GET.get("q") or "").strip()
    cat = (request.GET.get("cat") or "").strip()

    pages_qs = src.pages.all()
    if cat in ["blog", "product", "info"]:
        pages_qs = pages_qs.filter(category=cat)
    if q:
        pages_qs = pages_qs.filter(url__icontains=q)

    if request.method == "POST":
        action = request.POST.get("action", "")

        # actions that update selection without sending all ids
        if action == "select_all":
            src.pages.update(selected=True)
            messages.success(request, "Selected all URLs.")
        elif action == "clear_all":
            src.pages.update(selected=False)
            messages.success(request, "Cleared all selections.")
        elif action == "select_filtered":
            pages_qs.update(selected=True)
            messages.success(request, "Selected all filtered URLs.")
        elif action == "clear_filtered":
            pages_qs.update(selected=False)
            messages.success(request, "Cleared filtered selections.")
        elif action == "save_page":
            # update only current page’s displayed items
            displayed = (request.POST.get("displayed_ids") or "").split(",")
            displayed = [int(x) for x in displayed if x.isdigit()]
            checked = request.POST.getlist("page_ids")  # only checked
            checked = set(int(x) for x in checked if x.isdigit())

            # set selected True/False for displayed
            src.pages.filter(id__in=displayed).update(selected=False)
            if checked:
                src.pages.filter(id__in=checked).update(selected=True)

            messages.success(request, "Selection updated for this page.")
        elif action == "get_info":
            selected_count = src.pages.filter(selected=True).count()
            if selected_count == 0:
                messages.error(request, "Select at least 1 URL to continue.")
            else:
                src.selected_pages = selected_count
                src.processed_pages = 0
                src.status = "pending"
                src.error_message = ""
                src.save(update_fields=["selected_pages", "processed_pages", "status", "error_message"])
                messages.success(request, "Started scraping job. You can track progress in Source History.")
                return redirect(f"/sources/{src.id}/")

        # refresh counts
        src.total_pages = src.pages.count()
        src.selected_pages = src.pages.filter(selected=True).count()
        src.save(update_fields=["total_pages", "selected_pages"])
        return redirect(request.get_full_path())

    paginator = Paginator(pages_qs.order_by("category", "url"), 25)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    selected_count = src.pages.filter(selected=True).count()
    counts = src.pages.values("category").annotate(n=Count("id"))

    return render(request, "sources/website_select_pages.html", {
        "src": src,
        "page_obj": page_obj,
        "q": q,
        "cat": cat,
        "selected_count": selected_count,
        "counts": counts,
    })
