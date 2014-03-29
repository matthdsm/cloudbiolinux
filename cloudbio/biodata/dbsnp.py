"""Download variation data from dbSNP and install within directory structure.

Uses Broad's GATK resource bundles:

 http://www.broadinstitute.org/gsa/wiki/index.php/GATK_resource_bundle

Retrieves dbSNP plus training data for variant recalibration:
  - dbsnp_132.hg19.vcf.gz
  - hapmap_3.3.hg19.sites.vcf
  - 1000G_omni2.5.hg19.sites.vcf
  - Mills_and_1000G_gold_standard.indels.hg19.sites.vcf

For MuTect and cancer calling:
  - cosmic
"""
import os

from fabric.api import env, warn_only
from fabric.contrib.files import cd

from cloudbio.custom import shared

def download_dbsnp(genomes, bundle_version, dbsnp_version):
    """Download and install dbSNP variation data for supplied genomes.
    """
    folder_name = "variation"
    genome_dir = os.path.join(env.data_files, "genomes")
    for (orgname, gid, manager) in ((o, g, m) for (o, g, m) in genomes
                                    if m.config.get("dbsnp", False)):
        vrn_dir = os.path.join(genome_dir, orgname, gid, folder_name)
        if not env.safe_exists(vrn_dir):
            env.safe_run('mkdir -p %s' % vrn_dir)
        with cd(vrn_dir):
            if gid in ["GRCh37", "hg19"]:
                _dbsnp_human(env, gid, manager, bundle_version, dbsnp_version)
            elif gid in ["mm10"]:
                _dbsnp_mouse(env, gid)

def _dbsnp_mouse(env, gid):
    """Retrieve resources for mouse variant analysis from custom S3 biodata bucket.
    """
    remote_dir = "https://s3.amazonaws.com/biodata/variants/"
    files = {"mm10": ["mm10-dbSNP-2013-09-12.vcf"]}
    for f in files[gid]:
        for ext in ["", ".idx"]:
            fname = f + ext
            if not env.safe_exists(fname):
                out_file = shared._remote_fetch(env, "%s%s.gz" % (remote_dir, fname))
                env.safe_run("gunzip %s" % out_file)

def _dbsnp_human(env, gid, manager, bundle_version, dbsnp_version):
    """Retrieve resources for human variant analysis from Broad resource bundles.
    """
    to_download = ["dbsnp_{ver}".format(ver=dbsnp_version),
                   "hapmap_3.3",
                   "1000G_omni2.5",
                   "1000G_phase1.snps.high_confidence",
                   "Mills_and_1000G_gold_standard.indels"]
    for dl_name in to_download:
        for ext in [""]:
            _download_broad_bundle(manager.dl_name, bundle_version, dl_name, ext)
    _download_cosmic(gid)
    # XXX Wait to get this by default until it is used more widely
    #_download_background_vcf(gid)

def _download_broad_bundle(gid, bundle_version, name, ext):
    broad_fname = "{name}.{gid}.vcf{ext}".format(gid=gid, name=name, ext=ext)
    fname = broad_fname.replace(".{0}".format(gid), "").replace(".sites", "") + ".gz"
    base_url = "ftp://gsapubftp-anonymous:@ftp.broadinstitute.org/bundle/" + \
               "{bundle}/{gid}/{fname}.gz".format(
                   bundle=bundle_version, fname=broad_fname, gid=gid)
    # compress and prepare existing uncompressed versions
    if env.safe_exists(fname.replace(".vcf.gz", ".vcf")):
        env.safe_run("bgzip %s" % fname.replace(".vcf.gz", ".vcf"))
        env.safe_run("tabix -f -p vcf %s" % fname)
    # otherwise, download and bgzip and tabix index
    if not env.safe_exists(fname):
        out_file = shared._remote_fetch(env, base_url, allow_fail=True)
        if out_file:
            env.safe_run("gunzip -c %s | bgzip -c > %s" % (out_file, fname))
            env.safe_run("tabix -f -p vcf %s" % fname)
            env.safe_run("rm -f %s" % out_file)
        else:
            env.logger.warn("dbSNP resources not available for %s" % gid)
    # clean up old files
    for ext in [".vcf", ".vcf.idx"]:
        if env.safe_exists(fname.replace(".vcf.gz", ext)):
            env.safe_run("rm -f %s" % (fname.replace(".vcf.gz", ext)))
    return fname

def _download_cosmic(gid):
    """Prepared versions of COSMIC, pre-sorted and indexed.
    utils/prepare_cosmic.py handles the work of creating the VCFs from standard
    COSMIC resources.
    """
    base_url = "https://s3.amazonaws.com/biodata/variants"
    version = "v68"
    supported = ["hg19", "GRCh37"]
    if gid in supported:
        url = "%s/cosmic-%s-%s.vcf.gz" % (base_url, version, gid)
        fname = os.path.basename(url)
        if not env.safe_exists(fname):
            shared._remote_fetch(env, url)
        if not env.safe_exists(fname + ".tbi"):
            shared._remote_fetch(env, url + ".tbi")

def _download_background_vcf(gid):
    """Download background file of variant to use in calling.
    """
    base_url = "https://s3.amazonaws.com/biodata/variants"
    base_name = "background-diversity-1000g.vcf"
    if gid in ["GRCh37"] and not env.safe_exists("{0}.gz".format(base_name)):
        for ext in ["gz", "gz.tbi"]:
            shared._remote_fetch(env, "{0}/{1}.{2}".format(base_url, base_name, ext))
